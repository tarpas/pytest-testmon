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
import kotlin.collections.ArrayList


/**
 * RuntimeInfo project component.
 */
class RuntimeInfoProjectComponent(private val project: Project) : ProjectComponent {

    private lateinit var virtualFileListener: VirtualFileListener

    companion object {
        const val COMPONENT_NAME = "RuntimeInfoProjectComponent"
    }

    override fun getComponentName(): String {
        return COMPONENT_NAME
    }

    override fun projectOpened() {
        val contentRoots = ProjectRootManager.getInstance(project).contentRoots

        for (contentRoot in contentRoots) {
            VfsUtilCore.iterateChildrenRecursively(contentRoot, null, {
                if (it.name == DATABASE_FILE_NAME) {
                    addRuntimeInfoFileToModule(project, it)
                }

                true
            })
        }

        virtualFileListener = buildDatabasesListener()

        VirtualFileManager.getInstance().addVirtualFileListener(virtualFileListener)

        project.messageBus.connect().subscribe(ProjectTopics.MODULES, buildModuleListener())
    }

    /**
     * This steps needed to prevent firing events on closed project(s).
     */
    override fun projectClosed() {
        VirtualFileManager.getInstance().removeVirtualFileListener(virtualFileListener)

        project.messageBus.connect().disconnect()
    }

    private fun buildDatabasesListener(): VirtualFileListener {
        return object : VirtualFileListener {
            override fun fileCreated(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val runtimeInfoFilePath = it.path

                        addRuntimeInfoFileToModule(project, it)

                        invalidateCache(it)

                        logInfoMessage("runtime-info file created: $runtimeInfoFilePath", project)

                        addRuntimeInfoFileToToolWindow(runtimeInfoFilePath)
                    }

                    true
                })
            }

            override fun beforeFileDeletion(event: VirtualFileEvent) {
                VfsUtilCore.iterateChildrenRecursively(event.file, null, {
                    if (it.name == DATABASE_FILE_NAME) {
                        val runtimeInfoFilePath = it.path

                        removeRuntimeInfoFileFromModule(it)

                        invalidateCache(it)

                        logInfoMessage("runtime-info file deleted: $runtimeInfoFilePath", project)

                        removeRuntimeInfoFileFromToolWindow(runtimeInfoFilePath)
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
    }

    private fun buildModuleListener(): ModuleListener {
        return object : ModuleListener {
            override fun moduleAdded(project: Project, module: Module) {
                val rootManager = ModuleRootManager.getInstance(module)

                for (rootVirtualFile in rootManager.contentRoots) {
                    VfsUtilCore.iterateChildrenRecursively(rootVirtualFile, null, {
                        if (it.name == DATABASE_FILE_NAME) {
                            val runtimeInfoFilePath = it.path

                            addRuntimeInfoFileToModule(module, it)

                            addRuntimeInfoFileToToolWindow(runtimeInfoFilePath)
                        }

                        true
                    })
                }
            }
        }
    }

    private fun getToolWindow(): ToolWindow? {
        val toolWindowManager = ToolWindowManager.getInstance(project) ?: return null

        return toolWindowManager.getToolWindow("Runtime Info")
    }

    private fun getRuntimeInfoListPanel(): RuntimeInfoListPanel? {
        val runtimeInfoToolWindow = getToolWindow() ?: return null

        val content = runtimeInfoToolWindow.contentManager.getContent(0)
                ?: return null

        return content.component as RuntimeInfoListPanel
    }

    private fun addRuntimeInfoFileToToolWindow(runtimeInfoFile: String) {
        getRuntimeInfoListPanel()?.addFile(runtimeInfoFile)
    }

    private fun removeRuntimeInfoFileFromToolWindow(runtimeInfoFile: String) {
        getRuntimeInfoListPanel()?.removeFile(runtimeInfoFile)
    }

    private fun addRuntimeInfoFileToModule(project: Project, virtualFile: VirtualFile) {
        val module = ModuleUtil.findModuleForFile(virtualFile, project) ?: return

        addRuntimeInfoFileToModule(module, virtualFile)
    }

    private fun addRuntimeInfoFileToModule(module: Module, virtualFile: VirtualFile) {
        var list = getModuleRuntimeInfoFiles(module)

        if (list == null) {
            list = ArrayList()
        }

        val moduleRuntimeInfoFiles = list as MutableList<String>

        moduleRuntimeInfoFiles.add(virtualFile.path)

        module.putUserData(MODULE_DATABASE_FILES_KEY, moduleRuntimeInfoFiles)
    }

    private fun removeRuntimeInfoFileFromModule(virtualFile: VirtualFile) {
        val module = ModuleUtil.findModuleForFile(virtualFile, project) ?: return

        val list = getModuleRuntimeInfoFiles(module) ?: return
        val moduleRuntimeInfoFiles = list as MutableList<String>

        moduleRuntimeInfoFiles.remove(virtualFile.path)

        module.putUserData(MODULE_DATABASE_FILES_KEY, moduleRuntimeInfoFiles)
    }

    private fun invalidateCache(virtualFile: VirtualFile) {
        val module = ModuleUtil.findModuleForFile(virtualFile, project)

        if (module != null) {
            val cacheService = ModuleServiceManager.getService(module, Cache::class.java)

            cacheService?.clear()
        }
    }
}