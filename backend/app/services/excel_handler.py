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
                    'name': ['company name', 'company', 'business name'],
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
            # Define column order
            columns = [
                'name',
                'uen',
                'address',
                'phone',
                'email',
                'founder',
                'website',
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
            df.columns = [
                'Company Name',
                'UEN Number',
                'Address',
                'Phone Number',
                'Email Address',
                'Founder/Director',
                'Website',
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
                    worksheet.column_dimensions[chr(64 + idx)].width = min(max_length + 2, 50)

            output.seek(0)
            return output

        except Exception as e:
            raise ValueError(f"Error creating Excel file: {str(e)}")

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
