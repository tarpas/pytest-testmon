import React from "react";

function Tabs({ activeTab, setActiveTab, testCount, fileCount }) {
    const tabs = [
        { id: 'summary', label: 'Summary' },
        { id: 'tests', label: `Tests (${testCount})` },
        { id: 'files', label: `Files (${fileCount})` }
    ];

    return (
        <div className="flex bg-gray-50 border-b-2 border-gray-200">
            {tabs.map(tab => (
                <button
                    key={tab.id}
                    className={`flex-1 p-5 text-center font-semibold transition-all relative ${
                        activeTab === tab.id
                            ? 'text-indigo-500 bg-white'
                            : 'text-gray-500 hover:bg-indigo-50 hover:text-indigo-500'
                    }`}
                    onClick={() => setActiveTab(tab.id)}
                >
                    {tab.label}
                    {activeTab === tab.id && (
                        <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500" />
                    )}
                </button>
            ))}
        </div>
    );
}

export default Tabs;