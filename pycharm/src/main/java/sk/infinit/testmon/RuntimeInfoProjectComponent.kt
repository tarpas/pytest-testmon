package sk.infinit.testmon

import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFileEvent
import com.intellij.openapi.vfs.VirtualFileListener
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.psi.search.FilenameIndex
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.util.indexing.FileBasedIndex

/**
 * RuntimeInfo project component.
 */
class RuntimeInfoProjectComponent(private val project: Project) : ProjectComponent {

    /**
     * Contains set of runtime info files for all projects in current window.
     */
    private val runtimeInfoFiles = HashSet<String>()

    /**
     * Companion object for constants.
     */
    companion object {
        const val COMPONENT_NAME = "RuntimeInfoProjectComponent"

        const val DATABASE_FILE_NAME = ".runtime_info0"
    }

    override fun getComponentName(): String {
        return COMPONENT_NAME
    }

    /**
     * Initialize RuntimeInfoProjectComponent on project open.
     */
    override fun projectOpened() {
        val containingFiles = FileBasedIndex.getInstance()
                .getContainingFiles(FilenameIndex.NAME, DATABASE_FILE_NAME, GlobalSearchScope.allScope(project))

        for (runtimeInfoVFile in containingFiles) {
            runtimeInfoFiles.add(runtimeInfoVFile.path)
        }

        VirtualFileManager.getInstance().addVirtualFileListener(object : VirtualFileListener {
            override fun fileCreated(event: VirtualFileEvent) {
                runtimeInfoFiles.add(event.file.path)
            }

            override fun fileDeleted(event: VirtualFileEvent) {
                runtimeInfoFiles.remove(event.file.path)
            }

            override fun contentsChanged(event: VirtualFileEvent) {
//                val runtimeInfoToolWindow = ToolWindowManager.getInstance(project).getToolWindow("Runtime Info")
                //JOptionPane.showMessageDialog(null, "contentsChanged ${event.fileName}")
            }
        })
    }

    /**
     * Return copy of [runtimeInfoFiles] as list.
     */
    fun getRuntimeInfoFiles(): List<String> = runtimeInfoFiles.toList()
}