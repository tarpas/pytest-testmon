import React from "react";

function Header() {
    return (
        <div className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white p-8 text-center">
            <h1 className="text-4xl font-light mb-2">Testmon Multi-Project Visualizer</h1>
            <p className="text-lg opacity-90">Intelligent test selection across repositories and jobs</p>
        </div>
    );
}

export default Header;