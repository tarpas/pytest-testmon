import {RefreshCw} from "lucide-react";
import React from "react";

function SelectorBar({ repos, currentRepo, currentJob, selectedRepo, onRepoChange, onJobChange, onRefresh }) {
    return (
        <div className="bg-gray-50 p-5 border-b-2 border-gray-200 flex gap-5 items-end flex-wrap">
            <div className="flex-1 min-w-[250px]">
                <label className="block font-semibold text-gray-600 mb-2 text-sm uppercase tracking-wide">
                    Repository
                </label>
                <select
                    className="w-full p-3 text-base border-2 border-gray-300 rounded-lg bg-white cursor-pointer transition-all hover:border-indigo-500 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    value={currentRepo || ''}
                    onChange={(e) => {
                        onRepoChange(e.target.value || null);
                        onJobChange(null);
                    }}
                >
                    <option value="">Select a repository</option>
                    {repos.map(repo => (
                        <option key={repo.id} value={repo.id}>
                            {repo.name} ({repo.jobs.length} jobs)
                        </option>
                    ))}
                </select>
            </div>

            <div className="flex-1 min-w-[250px]">
                <label className="block font-semibold text-gray-600 mb-2 text-sm uppercase tracking-wide">
                    Job
                </label>
                <select
                    className="w-full p-3 text-base border-2 border-gray-300 rounded-lg bg-white cursor-pointer transition-all hover:border-indigo-500 focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed"
                    value={currentJob || ''}
                    onChange={(e) => onJobChange(e.target.value || null)}
                    disabled={!selectedRepo}
                >
                    <option value="">Select a job</option>
                    {selectedRepo?.jobs.map(job => (
                        <option key={job.id} value={job.id}>
                            {job.id} (updated: {new Date(job.last_updated).toLocaleString()})
                        </option>
                    ))}
                </select>
            </div>

            <button
                className="px-6 py-3 bg-indigo-500 text-white rounded-lg cursor-pointer font-semibold transition-all hover:bg-indigo-600 hover:-translate-y-0.5 hover:shadow-lg flex items-center gap-2"
                onClick={onRefresh}
            >
                <RefreshCw size={20} />
                Refresh
            </button>
        </div>
    );
}

export default SelectorBar;