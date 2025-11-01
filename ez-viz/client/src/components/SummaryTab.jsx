import React from "react";
import EnvItem from "./EnvItem.jsx";
import StatCard from "./StatCard.jsx";

function SummaryTab({ summary, allTests, currentRepo, currentJob }) {
    const passed = allTests.filter(t => !t.failed).length;
    const failed = allTests.filter(t => t.failed).length;

    return (
        <div className="animate-fadeIn">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                <StatCard
                    title="Tests"
                    value={summary.test_count}
                    label={`${passed} passed, ${failed} failed`}
                />
                <StatCard
                    title="Files Tracked"
                    value={summary.file_count}
                    label="monitored for changes"
                />
                <StatCard
                    title="Repository"
                    value={currentRepo?.split('/').pop() || 'N/A'}
                    label={currentJob}
                    smallValue
                />
            </div>

            <div className="bg-gray-50 p-5 rounded-lg border-l-4 border-indigo-500">
                <h3 className="text-gray-700 mb-4 text-lg font-semibold">Environment Information</h3>
                <EnvItem label="Environment" value={summary.environment.name} />
                <EnvItem label="Python Version" value={summary.environment.python_version} />
                <EnvItem label="Packages" value={summary.environment.packages || 'N/A'} />
            </div>
        </div>
    );
}

export default SummaryTab;