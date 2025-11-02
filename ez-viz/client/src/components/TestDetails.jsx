import React from "react";
import EnvItem from "./EnvItem.jsx";
import {formatDuration, getStatusText} from "./utils.jsx";

function TestDetails({ test, dependencies }) {
    return (
        <>
            <div className="mb-6">
                <EnvItem label="Status" value={getStatusText()} />
                <EnvItem label="Duration" value={formatDuration(test.duration)} />
            </div>

            <div>
                <h3 className="text-gray-700 mb-4 pb-2 border-b-2 border-gray-200 text-xl">
                    Dependencies ({dependencies.length})
                </h3>
                {dependencies.map((dep, idx) => (
                    <div key={idx} className="bg-gray-50 p-4 rounded-lg mb-3 border-l-4 border-indigo-500">
                        <div className="font-semibold text-gray-700 mb-2">📄 {dep.filename}</div>
                        <div className="text-sm text-gray-600 flex gap-5 flex-wrap mb-2">
                            <span>SHA: {dep.fsha ? dep.fsha.substring(0, 8) : 'N/A'}</span>
                            <span>{dep.checksums.length} blocks</span>
                        </div>
                        <div className="mt-2 p-2 bg-white rounded text-xs font-mono break-all">
                            Checksums: [{dep.checksums.join(', ')}]
                        </div>
                    </div>
                ))}
            </div>
        </>
    );
}

export default TestDetails;