import { useState, useEffect, useRef } from 'react';
import Upload from './components/Upload';
import Processing from './components/Processing';
import RecoveryPrompt from './components/RecoveryPrompt';
import { enrichCompaniesWithProgress } from './api/streamClient';
import { recoveryStorage, type RecoverySession } from './services/recoveryStorage';
import { generateExcelBlob, downloadBlob } from './utils/excelGenerator';

interface ProgressState {
  current: number;
  total: number;
  company: string;
}

function App() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recoverySession, setRecoverySession] = useState<RecoverySession | null>(null);
  const [progress, setProgress] = useState<ProgressState>({ current: 0, total: 0, company: '' });

  // Track current session ID for disruption handling
  const currentSessionRef = useRef<string | null>(null);
  const originalFilenameRef = useRef<string>('');

  // Check for incomplete session on mount
  useEffect(() => {
    const checkRecovery = async () => {
      try {
        await recoveryStorage.init();
        const session = await recoveryStorage.getIncompleteSession();
        if (session && session.processedCompanies.length > 0) {
          setRecoverySession(session);
        }
      } catch (err) {
        console.error('Failed to check for recovery session:', err);
      }
    };
    checkRecovery();
  }, []);

  // Handle page visibility and beforeunload for disruption detection
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isProcessing && currentSessionRef.current) {
        // Mark session as interrupted before page unloads
        recoveryStorage.markInterrupted(currentSessionRef.current);
        e.preventDefault();
        e.returnValue = '';
      }
    };

    const handleVisibilityChange = () => {
      // On mobile, tab hidden often means app will be killed
      if (document.visibilityState === 'hidden' && isProcessing && currentSessionRef.current) {
        recoveryStorage.markInterrupted(currentSessionRef.current);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isProcessing]);

  const handleFileUpload = async (file: File) => {
    setIsProcessing(true);
    setError(null);
    setProgress({ current: 0, total: 0, company: '' });
    originalFilenameRef.current = file.name;

    await enrichCompaniesWithProgress(
      file,
      // Progress callback
      async (event) => {
        console.log('[App] Progress event received:', event.type, event);
        try {
          if (event.type === 'session_start') {
            currentSessionRef.current = event.session_id;

            // Update UI FIRST before async storage operations
            console.log('[App] Setting progress for session_start:', event.total_companies);
            setProgress({ current: 0, total: event.total_companies, company: '' });

            // Then try to save to IndexedDB (non-blocking for UI)
            try {
              await recoveryStorage.saveSession({
                sessionId: event.session_id,
                originalFilename: event.original_filename,
                totalCompanies: event.total_companies,
                processedCompanies: [],
                startedAt: Date.now(),
                lastUpdatedAt: Date.now(),
                status: 'in_progress',
              });
              console.log('[App] Session saved to IndexedDB');
            } catch (storageErr) {
              console.warn('[App] Failed to save session to IndexedDB:', storageErr);
            }
          } else if (event.type === 'company_processed') {
            // Update UI FIRST
            console.log('[App] Setting progress for company:', event.data.name);
            setProgress({
              current: event.index + 1,
              total: event.total,
              company: event.data.name,
            });

            // Then try to store to IndexedDB (non-blocking for UI)
            try {
              await recoveryStorage.addProcessedCompany(currentSessionRef.current!, event.data);
            } catch (storageErr) {
              console.warn('[App] Failed to save company to IndexedDB:', storageErr);
            }
          } else if (event.type === 'complete') {
            // Get all processed data and generate Excel
            const session = await recoveryStorage.getSession(currentSessionRef.current!);
            if (session && session.processedCompanies.length > 0) {
              const blob = generateExcelBlob(
                session.processedCompanies,
                session.originalFilename
              );
              downloadBlob(blob, `enriched_${session.originalFilename}`);

              // Clear the session after successful download
              await recoveryStorage.clearSession(session.sessionId);
            }

            currentSessionRef.current = null;
            setIsProcessing(false);
          }
        } catch (err) {
          console.error('Error handling progress event:', err);
        }
      },
      // Error callback
      async (err) => {
        console.error('Enrichment stream error:', err);

        // Mark session as interrupted
        if (currentSessionRef.current) {
          await recoveryStorage.markInterrupted(currentSessionRef.current);

          // Check if there's recoverable data
          const session = await recoveryStorage.getIncompleteSession();
          if (session && session.processedCompanies.length > 0) {
            setRecoverySession(session);
          }
        }

        setError(`Connection error: ${err.message}. Your progress has been saved.`);
        setIsProcessing(false);
        currentSessionRef.current = null;
      }
    );
  };

  const handleRecover = async () => {
    if (recoverySession) {
      // Generate Excel from stored data
      const blob = generateExcelBlob(
        recoverySession.processedCompanies,
        recoverySession.originalFilename
      );
      downloadBlob(blob, `partial_${recoverySession.originalFilename}`);

      // Clear the session
      await recoveryStorage.clearSession(recoverySession.sessionId);
      setRecoverySession(null);
      setError(null);
    }
  };

  const handleDiscard = async () => {
    if (recoverySession) {
      await recoveryStorage.clearSession(recoverySession.sessionId);
      setRecoverySession(null);
      setError(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Company Data Enrichment Platform
          </h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Upload your Excel file with company details (name, UEN, address) and get enriched data
            with contact information, emails, and founder details.
          </p>
        </div>

        {error && (
          <div className="max-w-2xl mx-auto mb-6">
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex">
                <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800">Error</h3>
                  <p className="mt-1 text-sm text-red-700">{error}</p>
                </div>
                <button
                  onClick={() => setError(null)}
                  className="ml-auto text-red-400 hover:text-red-600"
                >
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        )}

        {recoverySession ? (
          <RecoveryPrompt
            session={recoverySession}
            onRecover={handleRecover}
            onDiscard={handleDiscard}
          />
        ) : (
          <Upload onUpload={handleFileUpload} isProcessing={isProcessing} />
        )}

        {isProcessing && (
          <Processing
            currentIndex={progress.current}
            totalCompanies={progress.total}
            currentCompany={progress.company}
          />
        )}

        <div className="mt-16 max-w-3xl mx-auto">
          <h2 className="text-2xl font-semibold text-gray-900 mb-6 text-center">How It Works</h2>
          <div className="grid md:grid-cols-3 gap-6">
            <div className="bg-white rounded-lg p-6 shadow-sm">
              <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                <span className="text-blue-600 font-bold text-xl">1</span>
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Upload Excel</h3>
              <p className="text-gray-600 text-sm">
                Upload your Excel file containing company name, UEN number, and address.
              </p>
            </div>

            <div className="bg-white rounded-lg p-6 shadow-sm">
              <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                <span className="text-blue-600 font-bold text-xl">2</span>
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Processing</h3>
              <p className="text-gray-600 text-sm">
                Our system searches and extracts contact details for each company.
              </p>
            </div>

            <div className="bg-white rounded-lg p-6 shadow-sm">
              <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                <span className="text-blue-600 font-bold text-xl">3</span>
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Download</h3>
              <p className="text-gray-600 text-sm">
                Get your enriched Excel file with phone numbers, emails, and founder names.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
