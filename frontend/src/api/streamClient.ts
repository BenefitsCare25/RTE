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
  console.log('[SSE] Starting request to:', `${API_URL}/api/enrich-stream`);

  try {
    const response = await fetch(`${API_URL}/api/enrich-stream`, {
      method: 'POST',
      body: formData,
    });

    console.log('[SSE] Response status:', response.status);
    console.log('[SSE] Response headers:', Object.fromEntries(response.headers.entries()));

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
    let chunkCount = 0;

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        console.log('[SSE] Stream ended. Total chunks received:', chunkCount);
        // Stream ended - check if we have any remaining data in buffer
        if (buffer.trim()) {
          processBuffer(buffer, onProgress);
        }
        break;
      }

      chunkCount++;
      const chunk = decoder.decode(value, { stream: true });
      console.log(`[SSE] Chunk ${chunkCount} received:`, chunk.substring(0, 200));
      buffer += chunk;

      // Parse SSE events from buffer
      // SSE format can use \n\n, \r\n\r\n, or \r\r as event separators
      // Normalize all line endings first, then split by double newline
      const normalizedBuffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
      const events = normalizedBuffer.split('\n\n');
      // Keep the last incomplete chunk in buffer (but keep original buffer for proper byte tracking)
      // We need to track how much of the original buffer was consumed
      const lastEvent = events.pop() || '';
      buffer = lastEvent;

      for (const eventBlock of events) {
        processBuffer(eventBlock, onProgress);
      }
    }
  } catch (error) {
    console.error('[SSE] Error:', error);
    onError(error as Error);
  }
}

/**
 * Process a single SSE event block
 */
function processBuffer(eventBlock: string, onProgress: (event: ProgressEvent) => void): void {
  const lines = eventBlock.split('\n');
  console.log('[SSE] Processing event block:', eventBlock.substring(0, 100));

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      try {
        const data = JSON.parse(line.slice(6));
        console.log('[SSE] Parsed event:', data.type, data);
        onProgress(data);
      } catch (e) {
        console.error('[SSE] Failed to parse SSE data:', line, e);
      }
    }
  }
}
