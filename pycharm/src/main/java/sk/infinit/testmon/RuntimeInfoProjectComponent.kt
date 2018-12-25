package sk.infinit.testmon

import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.module.ModuleServiceManager
import com.intellij.openapi.module.ModuleUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.*
import com.intellij.openapi.wm.ToolWindowManager
import sk.infinit.testmon.services.cache.Cache
import sk.infinit.testmon.toolWindow.RuntimeInfoListPanel


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
        val contentRoots = ProjectRootManager.getInstance(project).contentRoots

        for (contentRoot in contentRoots) {
            VfsUtilCore.iterateChildrenRecursively(contentRoot, null, processFile(object: ProcessRuntimeInfoFile {
                override fun process(virtualFile: VirtualFile) {
                    runtimeInfoFiles.add(virtualFile.path)

                    val module = ModuleUtil.findModuleForFile(virtualFile, project) ?: return

                    module.putUserData(MODULE_DATABASE_FILE_KEY, virtualFile.path)
                }
            }))
        }

        VirtualFileManager.getInstance().addVirtualFileListener(object : VirtualFileListener {
            override fun fileCreated(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, processFile(object: ProcessRuntimeInfoFile {
                    override fun process(virtualFile: VirtualFile) {
                        runtimeInfoFiles.add(virtualFile.path)
                        getRuntimeInfoListPanel().listModel.addElement(virtualFile.path)

                        val module = ModuleUtil.findModuleForFile(virtualFile, project) ?: return

                        module.putUserData(MODULE_DATABASE_FILE_KEY, virtualFile.path)
                    }
                }))
            }

            override fun beforeFileDeletion(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, processFile(object: ProcessRuntimeInfoFile {
                    override fun process(virtualFile: VirtualFile) {
                        runtimeInfoFiles.remove(virtualFile.path)
                        getRuntimeInfoListPanel().listModel.removeElement(virtualFile.path)

                        val module = ModuleUtil.findModuleForFile(virtualFile, project) ?: return

                        module.putUserData(MODULE_DATABASE_FILE_KEY, null)
                    }
                }))
            }

            override fun contentsChanged(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, processFile(object: ProcessRuntimeInfoFile {
                    override fun process(virtualFile: VirtualFile) {
                        val module = ModuleUtil.findModuleForFile(virtualFile, project)
                                ?: return

                        val cacheService = ModuleServiceManager.getService(module, Cache::class.java)
                                ?: return

                        cacheService.clear()
                    }
                }))
            }
        })
    }

    /**
     * Common function for process virtual file events.
     */
    private fun processFile(processRuntimeInfoFile: ProcessRuntimeInfoFile): (VirtualFile) -> Boolean {
        return {
            if (it.name == DATABASE_FILE_NAME) {
                processRuntimeInfoFile.process(it)
            }

            true
        }
    }

    /**
     * Return copy of [runtimeInfoFiles] as list.
     */
    fun getRuntimeInfoFiles(): List<String> = runtimeInfoFiles.toList()

    /**
     * Get Runtime Info ToolWindow.
     */
    private fun getToolWindow() = ToolWindowManager.getInstance(project).getToolWindow("Runtime Info")

    /**
     * Get [RuntimeInfoListPanel] instance.
     */
    private fun getRuntimeInfoListPanel(): RuntimeInfoListPanel {
        val runtimeInfoToolWindow = getToolWindow()

        val content = runtimeInfoToolWindow.contentManager.getContent(0)

        return content?.component as RuntimeInfoListPanel
    }

    /**
     * Internal interface to process file operations for different cases (add, delete).
     */
    interface ProcessRuntimeInfoFile {
        fun process(virtualFile: VirtualFile)
    }
}