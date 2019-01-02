package sk.infinit.testmon.extensions

import com.intellij.codeInsight.daemon.RelatedItemLineMarkerInfo
import com.intellij.codeInsight.daemon.RelatedItemLineMarkerProvider
import com.intellij.psi.PsiElement
import com.intellij.codeInsight.navigation.NavigationGutterIconBuilder
import com.intellij.icons.AllIcons
import com.intellij.openapi.module.ModuleServiceManager
import com.intellij.openapi.module.ModuleUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.jetbrains.extensions.python.toPsi
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyStatement
import sk.infinit.testmon.*
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.services.cache.Cache

/**
 * Testmon RelatedItemLineMarkerProvider fod display gutter icons.
 */
class GutterIconRelatedItemLineMarkerProvider : RelatedItemLineMarkerProvider() {

    /**
     * Add Line Marker Information to Gutter area.
     */
    override fun collectNavigationMarkers(psiElement: PsiElement, resultCollection: MutableCollection<in RelatedItemLineMarkerInfo<PsiElement>>) {
        if (psiElement is PyStatement) {
            val project = psiElement.project

            val module = ModuleUtil.findModuleForFile(psiElement.containingFile)
                    ?: return

            val fileFullPath = getFileFullPath(project, psiElement.containingFile.virtualFile)
                    ?: return

            if (isRuntimeInfoDisabled(module, fileFullPath)) {
                return
            }

            val cacheService = ModuleServiceManager.getService(module, Cache::class.java)
                    ?: return

            val pyFileMarks = cacheService.getPyFileMarks(fileFullPath, FileMarkType.GUTTER_LINK) ?: return

            for (fileMark in pyFileMarks) {
                val targetVirtualFile = findVirtualFile(fileMark.targetPath)

                val fileMarkContent = fileMark.checkContent.trim()

                if (targetVirtualFile != null && fileMarkContent == psiElement.text) {
                    val targetPsiElement = findTargetPsiElement(fileMark, project, targetVirtualFile) ?: continue

                    val navigationGutterIconBuilder = NavigationGutterIconBuilder
                            .create(AllIcons.General.Error)
                            .setTarget(targetPsiElement)
                            .setTooltipText("File ${targetVirtualFile.name}, Line ${fileMark.targetLine}")

                    resultCollection.add(navigationGutterIconBuilder.createLineMarkerInfo(psiElement))
                }
            }
        }
    }

    /**
     * Get target PsiElement to navigate.
     */
    private fun findTargetPsiElement(fileMark: PyFileMark, project: Project, targetVirtualFile: VirtualFile): PsiElement? {
        val targetPsiFile = targetVirtualFile.toPsi(project) as PyFile

        val document = targetPsiFile.viewProvider.document ?: return null

        val targetLine = fileMark.targetLine + 1

        if (targetLine >= document.lineCount) {
            return null
        }

        return targetPsiFile.findElementAt(document.getLineStartOffset(targetLine))
    }
}