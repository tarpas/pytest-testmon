package sk.infinit.testmon

import com.intellij.ProjectTopics
import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.module.Module
import com.intellij.openapi.module.ModuleServiceManager
import com.intellij.openapi.module.ModuleUtil
import com.intellij.openapi.project.ModuleListener
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.vfs.*
import com.intellij.openapi.wm.ToolWindowManager
import sk.infinit.testmon.services.cache.Cache
import sk.infinit.testmon.toolWindow.RuntimeInfoListPanel
import com.intellij.openapi.roots.ModuleRootManager
import com.intellij.openapi.wm.ToolWindow


/**
 * RuntimeInfo project component.
 */
class RuntimeInfoProjectComponent(private val project: Project) : ProjectComponent {

    /**
     * Contains set of runtime info files for all projects in current window.
     */
    private val runtimeInfoFiles = HashSet<String>()

    private lateinit var virtualFileListener: VirtualFileListener

    companion object {
        const val COMPONENT_NAME = "RuntimeInfoProjectComponent"
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
            VfsUtilCore.iterateChildrenRecursively(contentRoot, null, {
                if (it.name == DATABASE_FILE_NAME) {
                    runtimeInfoFiles.add(it.path)

                    val module = ModuleUtil.findModuleForFile(it, project)

                    module?.putUserData(MODULE_DATABASE_FILE_KEY, it.path)
                }

                true
            })
        }

        virtualFileListener = object : VirtualFileListener {
            override fun fileCreated(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val runtimeInfoFilePath = it.path

                        runtimeInfoFiles.add(runtimeInfoFilePath)

                        val module = ModuleUtil.findModuleForFile(it, project)

                        module?.putUserData(MODULE_DATABASE_FILE_KEY, runtimeInfoFilePath)

                        logInfoMessage("Runtime Info: file created: $runtimeInfoFilePath", project)

                        getRuntimeInfoListPanel()?.listModel?.addElement(runtimeInfoFilePath)
                    }

                    true
                })
            }

            override fun beforeFileDeletion(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val runtimeInfoFilePath = it.path

                        runtimeInfoFiles.remove(runtimeInfoFilePath)

                        val module = ModuleUtil.findModuleForFile(it, project)

                        module?.putUserData(MODULE_DATABASE_FILE_KEY, null)

                        logInfoMessage("Runtime Info: file deleted: $runtimeInfoFilePath", project)

                        getRuntimeInfoListPanel()?.listModel?.removeElement(runtimeInfoFilePath)
                    }

                    true
                })
            }

            override fun contentsChanged(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val module = ModuleUtil.findModuleForFile(it, project)

                        if (module != null) {
                            val cacheService = ModuleServiceManager.getService(module, Cache::class.java)

                            cacheService?.clear()
                        }
                    }

                    true
                })
            }
        }

        VirtualFileManager.getInstance().addVirtualFileListener(virtualFileListener)

        project.messageBus.connect().subscribe(ProjectTopics.MODULES,
                object : ModuleListener {
                    override fun moduleAdded(project: Project, module: Module) {
                        val rootManager = ModuleRootManager.getInstance(module)

                        for (rootVirtualFile in rootManager.contentRoots) {
                            VfsUtilCore.iterateChildrenRecursively(rootVirtualFile, null, {
                                if (it.name == DATABASE_FILE_NAME) {
                                    val runtimeInfoFilePath = it.path

                                    runtimeInfoFiles.add(runtimeInfoFilePath)

                                    module.putUserData(MODULE_DATABASE_FILE_KEY, runtimeInfoFilePath)
                                }

                                true
                            })
                        }
                    }
                })
    }

    override fun projectClosed() {
        VirtualFileManager.getInstance().removeVirtualFileListener(virtualFileListener)

        project.messageBus.connect().disconnect()
    }

    fun getRuntimeInfoFiles(): List<String> = runtimeInfoFiles.toList()

    private fun getToolWindow(): ToolWindow? {
        val toolWindowManager = ToolWindowManager.getInstance(project) ?: return null

        return toolWindowManager.getToolWindow("Runtime Info")
    }

    /**
     * Get [RuntimeInfoListPanel] instance.
     */
    private fun getRuntimeInfoListPanel(): RuntimeInfoListPanel? {
        val runtimeInfoToolWindow = getToolWindow() ?: return null

        val content = runtimeInfoToolWindow.contentManager.getContent(0)
                ?: return null

        return content.component as RuntimeInfoListPanel
    }
}