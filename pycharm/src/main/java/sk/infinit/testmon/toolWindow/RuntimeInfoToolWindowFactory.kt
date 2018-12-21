package sk.infinit.testmon.toolWindow

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import sk.infinit.testmon.RuntimeInfoProjectComponent

/**
 * Factory for runtime info [ToolWindow].
 */
class RuntimeInfoToolWindowFactory : ToolWindowFactory {

    /**
     * Create list with registered (exists) runtime-info files.
     */
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val runtimeInfoListPanel = RuntimeInfoListPanel()

        val runtimeInfoProjectComponent = project
                .getComponent(RuntimeInfoProjectComponent::class.java) as RuntimeInfoProjectComponent

        for (runtimeInfoFile in runtimeInfoProjectComponent.getRuntimeInfoFiles()) {
            runtimeInfoListPanel.listModel.addElement(runtimeInfoFile)
        }

        val contentManager = toolWindow.contentManager

        val content = contentManager.factory.createContent(runtimeInfoListPanel, null, false)

        contentManager.addContent(content)
    }
}