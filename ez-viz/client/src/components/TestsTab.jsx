import React from "react";
import TestItem from "./TestItem.jsx";
import SearchBox from "./SearchBox.jsx";

function TestsTab({ tests, search, setSearch, showTestDetails }) {
    const filteredTests = tests.filter(test =>
        test.test_name.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="animate-fadeIn">
            <SearchBox
                value={search}
                onChange={setSearch}
                placeholder="🔍 Search tests..."
            />

            <div className="grid gap-4">
                {filteredTests.map(test => (
                    <TestItem key={test.id} test={test} onClick={() => showTestDetails(test.id)} />
                ))}
            </div>
        </div>
    );
}

export default TestsTab;