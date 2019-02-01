package sk.infinit.testmon.extensions

import com.intellij.codeInsight.daemon.RelatedItemLineMarkerInfo
import com.intellij.codeInsight.daemon.RelatedItemLineMarkerProvider
import com.intellij.psi.PsiElement
import com.intellij.codeInsight.navigation.NavigationGutterIconBuilder
import com.intellij.openapi.components.ServiceManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.jetbrains.extensions.python.toPsi
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyStatement
import sk.infinit.testmon.*
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.GutterIconType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.services.cache.Cache
import java.io.File

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

            val fileRelativePath = getVirtualFileRelativePath(project, psiElement.containingFile.virtualFile)
                    ?: return

            val cacheService = ServiceManager.getService(project, Cache::class.java)
                    ?: return

            val pyFileMarks = cacheService.getPyFileMarks(fileRelativePath, FileMarkType.GUTTER_LINK) ?: return

            for (fileMark in pyFileMarks) {
                val targetFileFullPath = project.basePath + File.separator + fileMark.targetPath
                val targetVirtualFile = findVirtualFile(targetFileFullPath)

                val fileMarkContent = fileMark.checkContent.trim()

                if (targetVirtualFile != null && fileMarkContent == psiElement.text) {
                    val targetPsiElement = findTargetPsiElement(fileMark, project, targetVirtualFile) ?: continue

                    val arrowIcon = if (fileMark.gutterLinkType == GutterIconType.DOWN.value) {
                        Icons.MOVE_UP_ARROW
                    } else {
                        Icons.MOVE_DOWN_ARROW
                    }

                    val navigationGutterIconBuilder = NavigationGutterIconBuilder
                            .create(arrowIcon)
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

        val targetLine = fileMark.targetLine

        val lineNumber = if (targetLine == document.lineCount) {
            targetLine - 1
        } else {
            targetLine
        }

        if (targetLine >= document.lineCount) {
            return null
        }

        return targetPsiFile.findElementAt(document.getLineStartOffset(lineNumber))
    }
}