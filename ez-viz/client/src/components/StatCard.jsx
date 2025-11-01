import React from "react";

function StatCard({ title, value, label, smallValue }) {
    return (
        <div className="bg-gradient-to-br from-indigo-500 to-purple-600 p-6 rounded-xl text-white shadow-lg">
            <h3 className="text-sm opacity-90 mb-2 uppercase tracking-wider">{title}</h3>
            <div className={`font-bold mb-1 ${smallValue ? 'text-xl' : 'text-4xl'}`}>{value}</div>
            <div className="text-sm opacity-80">{label}</div>
        </div>
    );
}
export default StatCard;