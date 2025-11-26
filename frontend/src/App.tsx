import { useState } from 'react';
import Upload from './components/Upload';
import Processing from './components/Processing';
import { enrichCompanies } from './api/client';

function App() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileUpload = async (file: File) => {
    setIsProcessing(true);
    setError(null);

    try {
      const enrichedFile = await enrichCompanies(file);

      // Download the enriched file
      const url = window.URL.createObjectURL(enrichedFile);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `enriched_${file.name}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

    } catch (err: any) {
      console.error('Enrichment error:', err);

      if (err.response?.data) {
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const error = JSON.parse(reader.result as string);
            setError(error.detail || 'An error occurred during processing');
          } catch {
            setError('An error occurred during processing');
          }
        };
        reader.readAsText(err.response.data);
      } else {
        setError(err.message || 'Failed to connect to the server');
      }
    } finally {
      setIsProcessing(false);
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
            Upload your Excel file with company details (name, UEN, address)
            and get enriched data with contact information, emails, and founder details.
          </p>
        </div>

        {error && (
          <div className="max-w-2xl mx-auto mb-6">
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex">
                <svg
                  className="h-5 w-5 text-red-400"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
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

        <Upload onUpload={handleFileUpload} isProcessing={isProcessing} />

        {isProcessing && <Processing />}

        <div className="mt-16 max-w-3xl mx-auto">
          <h2 className="text-2xl font-semibold text-gray-900 mb-6 text-center">
            How It Works
          </h2>
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
