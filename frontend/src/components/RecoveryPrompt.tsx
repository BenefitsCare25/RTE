/**
 * Recovery prompt component shown when an interrupted session is detected
 */

import type { RecoverySession } from '../services/recoveryStorage';

interface RecoveryPromptProps {
  session: RecoverySession;
  onRecover: () => void;
  onDiscard: () => void;
}

const RecoveryPrompt = ({ session, onRecover, onDiscard }: RecoveryPromptProps) => {
  const processedCount = session.processedCompanies.length;
  const totalCount = session.totalCompanies;
  const percentage = totalCount > 0 ? Math.round((processedCount / totalCount) * 100) : 0;

  // Format the timestamp
  const interruptedAt = new Date(session.lastUpdatedAt);
  const timeAgo = getTimeAgo(interruptedAt);

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="bg-yellow-50 border-2 border-yellow-300 rounded-lg p-6">
        <div className="flex items-start">
          <svg
            className="h-6 w-6 text-yellow-500 mt-0.5 flex-shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <div className="ml-4 flex-1">
            <h3 className="text-lg font-semibold text-yellow-800">
              Previous Session Interrupted
            </h3>
            <p className="mt-2 text-sm text-yellow-700">
              Your previous enrichment was interrupted {timeAgo}.{' '}
              <strong>
                {processedCount} of {totalCount} companies
              </strong>{' '}
              ({percentage}%) were processed successfully.
            </p>
            <p className="mt-1 text-xs text-yellow-600">File: {session.originalFilename}</p>

            {/* Progress bar showing how much was completed */}
            <div className="mt-3 w-full bg-yellow-200 rounded-full h-2">
              <div
                className="bg-yellow-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${percentage}%` }}
              ></div>
            </div>

            <div className="mt-4 flex gap-3 flex-wrap">
              <button
                onClick={onRecover}
                className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 font-medium transition-colors"
              >
                Download Partial Results ({processedCount} companies)
              </button>
              <button
                onClick={onDiscard}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium transition-colors"
              >
                Discard & Start Fresh
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Get a human-readable time ago string
 */
function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

  if (seconds < 60) {
    return 'just now';
  }

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
  }

  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
  }

  const days = Math.floor(hours / 24);
  return `${days} day${days !== 1 ? 's' : ''} ago`;
}

export default RecoveryPrompt;
