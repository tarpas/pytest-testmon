import {X} from "lucide-react";
import React from "react";

function Modal({ open, title, onClose, children }) {
    if (!open) return null;

    return (
        <div
            className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center animate-fadeIn"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl max-w-3xl w-11/12 max-h-[90vh] overflow-y-auto shadow-2xl animate-slideUp"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white p-6 flex justify-between items-center">
                    <h2 className="text-2xl font-semibold break-all flex-1">{title}</h2>
                    <button
                        className="w-10 h-10 flex items-center justify-center rounded-full transition-colors hover:bg-white hover:bg-opacity-20"
                        onClick={onClose}
                    >
                        <X size={28} />
                    </button>
                </div>
                <div className="p-6">{children}</div>
            </div>
        </div>
    );
}

export default Modal;
