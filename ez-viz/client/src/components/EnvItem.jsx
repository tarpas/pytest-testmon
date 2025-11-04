import React from "react";

function EnvItem({ label, value }) {
    return (
        <div className="flex py-2 border-b border-gray-200 last:border-b-0">
            <div className="font-semibold text-gray-600 min-w-[120px]">{label}:</div>
            <div className="text-gray-700 break-words">{value}</div>
        </div>
    );
}

export default EnvItem;