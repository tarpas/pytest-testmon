import React, { useState } from "react";
import { Save, ChevronDown, GripVertical } from "lucide-react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";

function TestManagementTab({ files , currentRepo , currentJob }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedTests, setSelectedTests] = useState([]);
  const [isOpen, setIsOpen] = useState(false);

  const [testList, setTestList] = useState(files);
  console.log("Test lists are", testList);
  const filteredTests = testList.filter((test) =>
    test.filename.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCheckboxChange = (testName) => {
    setSelectedTests((prev) =>
      prev.includes(testName)
        ? prev.filter((filename) => filename !== testName)
        : [...prev, testName]
    );
  };

  async function handleSave() {
  try {
    const response = await fetch('/api/client/testPreferences', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        repo_id:currentRepo,
        job_id:currentJob,
        selectedTests: selectedTests,
        
      })
    });

    if (response.ok) {
      const data = await response.json();
      alert(`Saved test choices:\n${selectedTests.join(", ")}`);
      console.log("Save successful:", data);
    } else {
      alert("Failed to save test preferences");
    }
  } catch (error) {
    console.error("Error saving preferences:", error);
    alert("Error saving test preferences");
  }
}

  const handleDragEnd = (result) => {
    if (!result.destination) return;
    const reordered = Array.from(testList);
    const [movedItem] = reordered.splice(result.source.index, 1);
    reordered.splice(result.destination.index, 0, movedItem);
    setTestList(reordered);
  };

  return (
    <div className="animate-fadeIn p-6 max-w-2xl mx-auto">
      <h3 className="text-lg font-medium text-gray-800 mb-2">Manage Tests</h3>
      <div className="relative mb-6">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center justify-between w-full px-5 py-2.5 rounded-md text-white text-sm font-medium bg-blue-600 hover:bg-blue-700 transition"
        >
          Select Tests
          <ChevronDown
            size={18}
            className={`ml-2 transition-transform ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {isOpen && (
          <ul className="absolute left-0 right-0 mt-2 bg-white border border-gray-200 shadow-lg rounded-md z-50 max-h-80 overflow-auto">
            <li className="p-2 border-b border-gray-100">
              <input
                type="text"
                placeholder="Search tests..."
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </li>

            {filteredTests.length > 0 ? (
              filteredTests.map((test) => {
                const id = `checkbox-${test.filename}`;
                return (
                  <li
                    key={id}
                    className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 cursor-pointer"
                  >
                    <label
                      htmlFor={id}
                      className="flex items-center gap-3 text-gray-700 text-sm font-medium cursor-pointer"
                    >
                      <input
                        id={id}
                        type="checkbox"
                        checked={selectedTests.includes(test.filename)}
                        onChange={() => handleCheckboxChange(test.filename)}
                        className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 cursor-pointer"
                      />
                      {test.filename}
                    </label>
                  </li>
                );
              })
            ) : (
              <li className="px-4 py-3 text-sm text-gray-500 text-center">
                No tests found
              </li>
            )}
          </ul>
        )}
      </div>

      <div className="mb-6">
        <h3 className="text-lg font-medium text-gray-800 mb-2">
          Test Priority Order
        </h3>
        <p className="text-gray-500 text-sm mb-3">
          Drag and drop to rank the tests by importance (top = highest
          priority).
        </p>

        <div className="bg-gray-50 border border-gray-200 rounded-lg shadow-sm">
          <DragDropContext onDragEnd={handleDragEnd}>
            <Droppable droppableId="tests">
              {(provided) => (
                <ul
                  {...provided.droppableProps}
                  ref={provided.innerRef}
                  className="divide-y divide-gray-200"
                >
                  {testList.map((test, index) => (
                    <Draggable
                      key={test.filename}
                      draggableId={test.filename}
                      index={index}
                    >
                      {(provided, snapshot) => (
                        <li
                          ref={provided.innerRef}
                          {...provided.draggableProps}
                          {...provided.dragHandleProps}
                          className={`flex items-center justify-between px-4 py-3 text-sm text-gray-700 bg-white ${
                            snapshot.isDragging ? "shadow-lg rounded-md" : ""
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <GripVertical className="text-gray-400" size={18} />
                            {test.filename}
                          </div>
                        </li>
                      )}
                    </Draggable>
                  ))}
                  {provided.placeholder}
                </ul>
              )}
            </Droppable>
          </DragDropContext>
        </div>
      </div>

      <div className="mb-6 flex gap-4 justify-center">
        <button
          onClick={handleSave}
          className="px-6 py-3 bg-indigo-500 text-white rounded-lg font-semibold hover:bg-indigo-600 transition-all flex items-center gap-2"
        >
          <Save size={20} />
          Save Choices
        </button>
      </div>

      <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-md shadow-sm">
        <p className="text-yellow-800 text-sm leading-relaxed">
          <strong>Tip:</strong> You can search and select tests to always run
          AND/OR you can prioritize test runs. Save your configuration for your
          CI pipeline.
        </p>
      </div>
    </div>
  );
}

export default TestManagementTab;
