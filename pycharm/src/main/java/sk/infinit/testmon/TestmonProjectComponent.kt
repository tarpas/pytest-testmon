package sk.infinit.testmon

import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.project.Project
import sk.infinit.testmon.database.DatabaseService

/**
 * Project component implementation for RuntimeInfo(Testmon) plugin.
 */
class TestmonProjectComponent(private val project: Project) : ProjectComponent {

    companion object {
        const val COMPONENT_NAME = "RuntimeInfoProjectComponent"
    }

    /**
     * Contains state of plugin extensions for current project.
     */
    var enabled: Boolean = true

    private var databaseService: DatabaseService? = null

    override fun getComponentName(): String {
        return COMPONENT_NAME
    }

    /**
     * Dispose DatabaseService on project closed.
     */
    override fun projectClosed() {
        databaseService?.dispose()
    }

    /**
     * Initialize DatabaseService on project open.
     */
    override fun projectOpened() {
        val databaseService = DatabaseService.getInstance()

        val isInitialized = databaseService.initialize(project.baseDir.path)

        if (!isInitialized) {
            enabled = false

            DatabaseService.getInstance().dispose()

            logErrorMessage("Not initialized.")
        } else {
            enabled = true
        }
    }
}