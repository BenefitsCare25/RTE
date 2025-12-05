import pandas as pd
from io import BytesIO
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

class ExcelHandler:
    """Service for handling Excel file operations"""

    @staticmethod
    def parse_excel(file_content: bytes) -> List[Dict[str, Any]]:
        """
        Parse uploaded Excel file and extract company information

        Args:
            file_content: Raw bytes of uploaded Excel file

        Returns:
            List of dictionaries containing company data
        """
        try:
            # Read Excel file from bytes
            df = pd.read_excel(BytesIO(file_content))

            # Normalize column names (lowercase, strip whitespace)
            df.columns = df.columns.str.strip().str.lower()

            # Check for required columns
            required_columns = ['name', 'uen', 'address']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                # Try alternative column names
                column_mapping = {
                    'name': ['company name', 'company', 'business name', 'entity_name', 'entity name'],
                    'uen': ['uen number', 'uen no', 'registration number', 'reg no'],
                    'address': ['company address', 'business address', 'location']
                }

                for required, alternatives in column_mapping.items():
                    if required in missing_columns:
                        for alt in alternatives:
                            if alt in df.columns:
                                df.rename(columns={alt: required}, inplace=True)
                                missing_columns.remove(required)
                                break

            # Handle split address columns (block, street_name, postal_code, etc.)
            if 'address' in missing_columns:
                address_components = ['block', 'street_name', 'level_no', 'unit_no', 'building_name', 'postal_code']
                if any(col in df.columns for col in address_components):
                    # Build address from components
                    def build_address(row):
                        parts = []

                        # Block number
                        if 'block' in df.columns and pd.notna(row.get('block')):
                            parts.append(f"BLK {row['block']}")

                        # Street name
                        if 'street_name' in df.columns and pd.notna(row.get('street_name')):
                            parts.append(str(row['street_name']))

                        # Unit number (level + unit)
                        unit_parts = []
                        if 'level_no' in df.columns and pd.notna(row.get('level_no')) and str(row.get('level_no')).lower() != 'na':
                            unit_parts.append(f"#{row['level_no']}")
                        if 'unit_no' in df.columns and pd.notna(row.get('unit_no')) and str(row.get('unit_no')).lower() != 'na':
                            if unit_parts:
                                unit_parts.append(f"-{row['unit_no']}")
                            else:
                                unit_parts.append(f"#{row['unit_no']}")
                        if unit_parts:
                            parts.append(''.join(unit_parts))

                        # Building name
                        if 'building_name' in df.columns and pd.notna(row.get('building_name')) and str(row.get('building_name')).lower() != 'na':
                            parts.append(str(row['building_name']))

                        # Postal code
                        if 'postal_code' in df.columns and pd.notna(row.get('postal_code')):
                            parts.append(f"Singapore {row['postal_code']}")

                        return ', '.join(parts) if parts else ''

                    df['address'] = df.apply(build_address, axis=1)
                    missing_columns.remove('address')

            if missing_columns:
                raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

            # Convert DataFrame to list of dictionaries
            companies = df[['name', 'uen', 'address']].to_dict('records')

            # Clean data
            for company in companies:
                company['name'] = str(company['name']).strip() if pd.notna(company['name']) else ''
                company['uen'] = str(company['uen']).strip() if pd.notna(company['uen']) else ''
                company['address'] = str(company['address']).strip() if pd.notna(company['address']) else ''

            # Filter out empty rows
            companies = [c for c in companies if c['name'] or c['uen']]

            return companies

        except Exception as e:
            raise ValueError(f"Error parsing Excel file: {str(e)}")

    @staticmethod
    def create_enriched_excel(companies: List[Dict[str, Any]]) -> BytesIO:
        """
        Create Excel file with enriched company data

        Args:
            companies: List of company dictionaries with enriched data

        Returns:
            BytesIO object containing the Excel file
        """
        try:
            # Define column order - updated with clear website/domain column and decision makers
            columns = [
                'name',
                'uen',
                'address',
                'phone_1',
                'phone_2',
                'phone_3',
                'email',
                'website',
                # Decision maker columns
                'dm1_name',
                'dm1_title',
                'dm1_linkedin',
                'dm2_name',
                'dm2_title',
                'dm2_linkedin',
                'dm3_name',
                'dm3_title',
                'dm3_linkedin',
                'discovered_urls',
                'status'
            ]

            # Create DataFrame
            df = pd.DataFrame(companies)

            # Ensure all columns exist
            for col in columns:
                if col not in df.columns:
                    df[col] = ''

            # Reorder columns
            df = df[columns]

            # Rename columns for better readability
            # Updated: "Website(s)" -> "Company Website" for clarity
            df.columns = [
                'Company Name',
                'UEN Number',
                'Address',
                'Phone 1',
                'Phone 2',
                'Phone 3',
                'Email Address',
                'Company Website',
                # Decision maker columns
                'Decision Maker 1 - Name',
                'Decision Maker 1 - Title',
                'Decision Maker 1 - LinkedIn',
                'Decision Maker 2 - Name',
                'Decision Maker 2 - Title',
                'Decision Maker 2 - LinkedIn',
                'Decision Maker 3 - Name',
                'Decision Maker 3 - Title',
                'Decision Maker 3 - LinkedIn',
                'Discovered URLs',
                'Enrichment Status'
            ]

            # Create Excel file in memory
            output = BytesIO()

            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Enriched Companies')

                # Auto-adjust column widths
                worksheet = writer.sheets['Enriched Companies']
                for idx, col in enumerate(df.columns, 1):
                    max_length = max(
                        df[col].astype(str).map(len).max(),
                        len(col)
                    )
                    # Use proper column letter conversion for columns beyond Z
                    col_letter = ExcelHandler._get_column_letter(idx)
                    worksheet.column_dimensions[col_letter].width = min(max_length + 2, 50)

            output.seek(0)
            return output

        except Exception as e:
            raise ValueError(f"Error creating Excel file: {str(e)}")

    @staticmethod
    def _get_column_letter(col_idx: int) -> str:
        """Convert column index to Excel column letter (1=A, 27=AA, etc.)"""
        result = ""
        while col_idx > 0:
            col_idx, remainder = divmod(col_idx - 1, 26)
            result = chr(65 + remainder) + result
        return result

    @staticmethod
    def validate_excel_file(filename: str, content_type: str) -> bool:
        """
        Validate if uploaded file is a valid Excel file

        Args:
            filename: Name of uploaded file
            content_type: MIME type of uploaded file

        Returns:
            True if valid Excel file, False otherwise
        """
        valid_extensions = ['.xlsx', '.xls']
        valid_content_types = [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel'
        ]

        has_valid_extension = any(filename.lower().endswith(ext) for ext in valid_extensions)
        has_valid_content_type = content_type in valid_content_types

        return has_valid_extension or has_valid_content_type
