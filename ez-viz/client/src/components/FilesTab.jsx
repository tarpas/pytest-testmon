import React from "react";
import FileItem from "./FileItem.jsx";
import SearchBox from "./SearchBox.jsx";

function FilesTab({ files, search, setSearch, showFileDetails }) {
    const filteredFiles = files.filter(file =>
        file.filename.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="animate-fadeIn">
            <SearchBox
                value={search}
                onChange={setSearch}
                placeholder="🔍 Search files..."
            />

            <div className="grid gap-4">
                {filteredFiles.map(file => (
                    <FileItem key={file.filename} file={file} onClick={() => showFileDetails(file.filename)} />
                ))}
            </div>
        </div>
    );
}

export default FilesTab;