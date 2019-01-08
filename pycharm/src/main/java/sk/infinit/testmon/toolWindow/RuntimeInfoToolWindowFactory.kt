package sk.infinit.testmon.toolWindow

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import sk.infinit.testmon.getRuntimeInfoFiles

/**
 * Factory for runtime info [ToolWindow].
 */
class RuntimeInfoToolWindowFactory : ToolWindowFactory {

    /**
     * Create list with registered (exists) runtime-info files.
     */
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val runtimeInfoListPanel = RuntimeInfoListPanel()

        val moduleRuntimeInfoFiles = getRuntimeInfoFiles(project)

        if (moduleRuntimeInfoFiles != null) {
            for (moduleRuntimeInfoFile in moduleRuntimeInfoFiles) {
                runtimeInfoListPanel.listModel.addElement(moduleRuntimeInfoFile)
            }
        }

        val contentManager = toolWindow.contentManager

        val content = contentManager.factory.createContent(runtimeInfoListPanel, null, false)

        contentManager.addContent(content)
    }
}