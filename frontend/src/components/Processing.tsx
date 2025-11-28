/**
 * Processing modal with real-time progress display
 */

interface ProcessingProps {
  currentIndex: number;
  totalCompanies: number;
  currentCompany?: string;
  successCount: number;
  failedCount: number;
}

const Processing = ({ currentIndex, totalCompanies, currentCompany, successCount, failedCount }: ProcessingProps) => {
  const progress = totalCompanies > 0 ? Math.round((currentIndex / totalCompanies) * 100) : 0;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 max-w-md w-full mx-4">
        <div className="text-center">
          {/* Spinner */}
          <div className="inline-block animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600 mb-4"></div>

          <h3 className="text-xl font-semibold text-gray-900 mb-2">Enriching Company Data</h3>

          {/* Progress indicator */}
          {totalCompanies > 0 ? (
            <>
              <p className="text-gray-600 mb-4">
                Processing company {currentIndex} of {totalCompanies}
              </p>

              {/* Success/Failed counters */}
              <div className="flex justify-center gap-8 mb-4">
                <div className="text-center">
                  <span className="text-2xl font-bold text-green-600">{successCount}</span>
                  <p className="text-xs text-gray-500">Successful</p>
                </div>
                <div className="text-center">
                  <span className="text-2xl font-bold text-red-500">{failedCount}</span>
                  <p className="text-xs text-gray-500">Failed</p>
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-gray-200 rounded-full h-2.5 mb-4">
                <div
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>

              {/* Percentage and next backup */}
              <div className="flex justify-between text-sm text-gray-500 mb-2">
                <span>{progress}% complete</span>
                <span className="text-gray-400">
                  Next backup: {currentIndex > 0 ? 10 - (currentIndex % 10) : 10} companies
                </span>
              </div>

              {/* Current company name */}
              {currentCompany && (
                <p className="text-sm text-gray-500 truncate mb-4" title={currentCompany}>
                  {currentCompany}
                </p>
              )}
            </>
          ) : (
            <p className="text-gray-600 mb-4">
              Please wait while we search and extract contact information...
            </p>
          )}

          {/* Recovery message */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-800">
              Progress is being saved automatically. If interrupted, you can recover your data on
              your next visit.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Processing;
