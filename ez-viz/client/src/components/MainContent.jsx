import Tabs from "./Tabs.jsx";
import TestsTab from "./TestsTab.jsx";
import FilesTab from "./FilesTab.jsx";
import SummaryTab from "./SummaryTab.jsx";
import React from "react";

function MainContent({ loading, error, summary, allTests, allFiles, activeTab, setActiveTab, testSearch, setTestSearch, fileSearch, setFileSearch, showTestDetails, showFileDetails, currentRepo, currentJob }) {
    if (loading) {
        return <div className="text-center p-16 text-gray-500 text-xl">Loading testmon data...</div>;
    }

    if (error) {
        return <div className="text-center p-16 text-red-600 text-lg">{error}</div>;
    }

    if (!summary) {
        return <div className="text-center p-16 text-gray-500 text-xl">Select a repository and job to view testmon data</div>;
    }

    return (
        <>
            <Tabs activeTab={activeTab} setActiveTab={setActiveTab} testCount={allTests.length} fileCount={allFiles.length} />

            <div className="p-8">
                {activeTab === 'summary' && (
                    <SummaryTab summary={summary} allTests={allTests} currentRepo={currentRepo} currentJob={currentJob} />
                )}

                {activeTab === 'tests' && (
                    <TestsTab tests={allTests} search={testSearch} setSearch={setTestSearch} showTestDetails={showTestDetails} />
                )}

                {activeTab === 'files' && (
                    <FilesTab files={allFiles} search={fileSearch} setSearch={setFileSearch} showFileDetails={showFileDetails} />
                )}
            </div>
        </>
    );
}

export default MainContent;