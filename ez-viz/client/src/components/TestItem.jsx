import React from "react";
import {formatDuration, getStatusText} from "./utils.jsx";

function TestItem({ test, onClick }) {
    const getStatusClass = () => {
        if (test.failed) return 'bg-red-100 text-red-800';
        if (test.forced) return 'bg-yellow-100 text-yellow-800';
        return 'bg-green-100 text-green-800';
    };

    return (
        <div
            className="bg-white border-2 border-gray-300 rounded-lg p-5 cursor-pointer transition-all hover:border-indigo-500 hover:shadow-lg hover:-translate-y-0.5"
            onClick={onClick}
        >
            <div className="flex justify-between items-center mb-2">
                <div className="text-lg font-semibold text-gray-700 flex-1 break-all">{test.test_name}</div>
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusClass()}`}>{() => getStatusText()}</span>
            </div>
            <div className="flex gap-5 text-sm text-gray-600">
                <span>{formatDuration(test.duration)}</span>
                <span>{test.dependency_count} dependencies</span>
            </div>
        </div>
    );
}

export default TestItem;