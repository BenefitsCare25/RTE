/**
 * SSE client for streaming enrichment progress from the backend
 */

import type { EnrichedCompany } from '../services/recoveryStorage';

export interface SessionStartEvent {
  type: 'session_start';
  session_id: string;
  total_companies: number;
  original_filename: string;
}

export interface CompanyProcessedEvent {
  type: 'company_processed';
  index: number;
  total: number;
  data: EnrichedCompany;
}

export interface CompleteEvent {
  type: 'complete';
  session_id: string;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export type ProgressEvent = SessionStartEvent | CompanyProcessedEvent | CompleteEvent | ErrorEvent;

/**
 * Upload file and stream enrichment progress via SSE
 *
 * @param file - The Excel file to upload
 * @param onProgress - Callback for progress events
 * @param onError - Callback for errors
 */
export async function enrichCompaniesWithProgress(
  file: File,
  onProgress: (event: ProgressEvent) => void,
  onError: (error: Error) => void
): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  try {
    const response = await fetch(`${API_URL}/api/enrich-stream`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      // Try to parse error message from response
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorMessage;
      } catch {
        // Ignore JSON parse errors
      }
      throw new Error(errorMessage);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('No response body');
    }

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        // Stream ended - check if we have any remaining data in buffer
        if (buffer.trim()) {
          processBuffer(buffer, onProgress);
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      // SSE format: "data: {...}\n\n"
      const events = buffer.split('\n\n');
      // Keep the last incomplete chunk in buffer
      buffer = events.pop() || '';

      for (const eventBlock of events) {
        processBuffer(eventBlock, onProgress);
      }
    }
  } catch (error) {
    onError(error as Error);
  }
}

/**
 * Process a single SSE event block
 */
function processBuffer(eventBlock: string, onProgress: (event: ProgressEvent) => void): void {
  const lines = eventBlock.split('\n');

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      try {
        const data = JSON.parse(line.slice(6));
        onProgress(data);
      } catch (e) {
        console.error('Failed to parse SSE data:', line, e);
      }
    }
  }
}
