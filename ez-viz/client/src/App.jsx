import React, { useState, useEffect } from 'react';
import Header from "./components/Header.jsx";
import SelectorBar from "./components/SelectorBar.jsx";
import Modal from "./components/Modal.jsx";
import MainContent from "./components/MainContent.jsx";
import TestDetails from "./components/TestDetails.jsx";
import FileDetails from "./components/FileDetails.jsx";

const API_BASE = '/api';

function App() {
    const [repos, setRepos] = useState([]);
    const [currentRepo, setCurrentRepo] = useState(null);
    const [currentJob, setCurrentJob] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [summary, setSummary] = useState(null);
    const [allTests, setAllTests] = useState([]);
    const [allFiles, setAllFiles] = useState([]);

    const [activeTab, setActiveTab] = useState('summary');
    const [testSearch, setTestSearch] = useState('');
    const [fileSearch, setFileSearch] = useState('');

    const [modal, setModal] = useState({ open: false, title: '', content: null });
    
    useEffect(() => {
        loadRepos();
        
    }, []);

    useEffect(() => {
        if (currentRepo && currentJob) {
            loadData();
        } else {
            setSummary(null);
        }
    }, [currentRepo, currentJob]);

    const loadRepos = async () => {
        try {
            const response = await fetch(`${API_BASE}/repos`);
            const data = await response.json();
            setRepos(data.repos || []);
            console.log("Response is",data)
        } catch (err) {
            console.error('Failed to load repos:', err);
            setError('Failed to load repositories');
        }
    };

    const loadData = async () => {
        if (!currentRepo || !currentJob) return;

        setLoading(true);
        setError(null);

        try {
            const [summaryData, testsData, filesData] = await Promise.all([
                fetch(`${API_BASE}/data/${currentRepo}/${currentJob}/summary`).then(r => r.json()),
                fetch(`${API_BASE}/data/${currentRepo}/${currentJob}/tests`).then(r => r.json()),
                fetch(`${API_BASE}/data/${currentRepo}/${currentJob}/files`).then(r => r.json())
            ]);
            console.log("Test data are",testsData)
            setSummary(summaryData);
            setAllTests(testsData.tests || []);
            setAllFiles(filesData.files || []);
            setActiveTab('summary');
        } catch (err) {
            setError('Failed to load testmon data: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    const showTestDetails = async (testId) => {
        try {
            const response = await fetch(`${API_BASE}/data/${currentRepo}/${currentJob}/test/${testId}`);
            const data = await response.json();

            setModal({
                open: true,
                title: data.test.test_name,
                content: <TestDetails test={data.test} dependencies={data.dependencies} />
            });
        } catch (err) {
            alert('Failed to load test details: ' + err.message);
        }
    };

    // why displaying same test twice?
    const showFileDetails = (filename) => {
        const relatedTests = allTests.filter(t =>
            t.test_name.includes(filename.replace('.py', ''))
        );

        setModal({
            open: true,
            title: filename,
            content: <FileDetails filename={filename} tests={relatedTests} />
        });
    };

    const selectedRepo = repos.find(r => r.id === currentRepo);

    return (
        <div className="min-h-screen bg-gradient-to-br from-indigo-500 to-purple-600 p-5">
            <div className="max-w-7xl mx-auto bg-white rounded-xl shadow-2xl overflow-hidden">
                <Header />

                <SelectorBar
                    repos={repos}
                    currentRepo={currentRepo}
                    currentJob={currentJob}
                    selectedRepo={selectedRepo}
                    onRepoChange={setCurrentRepo}
                    onJobChange={setCurrentJob}
                    onRefresh={loadRepos}
                />

                <MainContent
                    loading={loading}
                    error={error}
                    summary={summary}
                    allTests={allTests}
                    allFiles={allFiles}
                    activeTab={activeTab}
                    setActiveTab={setActiveTab}
                    testSearch={testSearch}
                    setTestSearch={setTestSearch}
                    fileSearch={fileSearch}
                    setFileSearch={setFileSearch}
                    showTestDetails={showTestDetails}
                    showFileDetails={showFileDetails}
                    currentRepo={currentRepo}
                    currentJob={currentJob}
                />
            </div>

            <Modal
                open={modal.open}
                title={modal.title}
                onClose={() => setModal({ open: false, title: '', content: null })}
            >
                {modal.content}
            </Modal>
        </div>
    );
}

export default App;