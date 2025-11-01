import React from "react";

function SearchBox({ value, onChange, placeholder }) {
    return (
        <div className="mb-5">
            <input
                type="text"
                className="w-full p-4 text-base border-2 border-gray-300 rounded-lg transition-all focus:outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder={placeholder}
            />
        </div>
    );
}

export default SearchBox;