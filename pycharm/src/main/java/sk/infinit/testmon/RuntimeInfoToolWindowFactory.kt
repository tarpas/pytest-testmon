package sk.infinit.testmon

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.components.JBList
import java.awt.BorderLayout
import javax.swing.JPanel
import javax.swing.DefaultListModel

/**
 *
 */
class RuntimeInfoToolWindowFactory : ToolWindowFactory {

    /**
     * List model for runtime info JBList.
     */
    val runtimeInfoFilesListModel = DefaultListModel<String>()

    /**
     * Create list with registered (exists) runtime-info files.
     */
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val mainPanel = JPanel(BorderLayout())

        val runtimeInfoProjectComponent = project
                .getComponent(RuntimeInfoProjectComponent::class.java) as RuntimeInfoProjectComponent

        for (runtimeInfoFile in runtimeInfoProjectComponent.getRuntimeInfoFiles()) {
            runtimeInfoFilesListModel.addElement(runtimeInfoFile)
        }

        val runtimeInfoFilesList = JBList(runtimeInfoFilesListModel)

        mainPanel.add(runtimeInfoFilesList, BorderLayout.CENTER)

        val content = toolWindow.contentManager.factory.createContent(mainPanel, null, false)

        toolWindow.contentManager.addContent(content)
    }
}