/**
 * Client-side Excel generation utility using SheetJS (xlsx)
 * Used for generating recovery downloads from stored data
 */

import * as XLSX from 'xlsx';
import type { EnrichedCompany } from '../services/recoveryStorage';

/**
 * Generate an Excel blob from enriched company data
 */
export function generateExcelBlob(companies: EnrichedCompany[], _filename: string): Blob {
  // Create workbook
  const wb = XLSX.utils.book_new();

  // Transform data to match expected column format
  const data = companies.map((c) => ({
    'Company Name': c.name,
    'UEN Number': c.uen,
    'Address': c.address,
    'Phone 1': c.phone_1,
    'Phone 2': c.phone_2,
    'Phone 3': c.phone_3,
    'Email Address': c.email,
    'Website(s)': c.website,
    'Enrichment Status': c.status,
  }));

  // Create worksheet
  const ws = XLSX.utils.json_to_sheet(data);

  // Set column widths for better readability
  ws['!cols'] = [
    { wch: 30 }, // Company Name
    { wch: 15 }, // UEN Number
    { wch: 40 }, // Address
    { wch: 15 }, // Phone 1
    { wch: 15 }, // Phone 2
    { wch: 15 }, // Phone 3
    { wch: 30 }, // Email Address
    { wch: 40 }, // Website(s)
    { wch: 40 }, // Enrichment Status
  ];

  // Add worksheet to workbook
  XLSX.utils.book_append_sheet(wb, ws, 'Enriched Companies');

  // Generate array buffer
  const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });

  // Create blob
  return new Blob([wbout], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

/**
 * Trigger browser download for a blob
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
