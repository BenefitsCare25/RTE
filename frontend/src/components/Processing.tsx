const Processing = () => {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 max-w-md w-full mx-4">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600 mb-4"></div>

          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            Enriching Company Data
          </h3>

          <p className="text-gray-600 mb-4">
            Please wait while we search and extract contact information...
          </p>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-800">
              This process may take a few minutes depending on the number of companies.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Processing;
