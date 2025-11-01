import React from "react";

function FileItem({ file, onClick }) {
    return (
        <div
            className="bg-white border-2 border-gray-300 rounded-lg p-5 cursor-pointer transition-all hover:border-indigo-500 hover:shadow-lg hover:-translate-y-0.5"
            onClick={onClick}
        >
            <div className="text-lg font-semibold text-gray-700 mb-2">📄 {file.filename}</div>
            <div className="flex gap-5 text-sm text-gray-600">
                <span>🧪 {file.test_count} tests</span>
                <span>🔖 {file.fingerprint_count} fingerprints</span>
            </div>
        </div>
    );
}

export default FileItem;