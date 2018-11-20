package sk.infinit.testmon.extensions

import com.intellij.codeInsight.daemon.RelatedItemLineMarkerInfo
import com.intellij.codeInsight.daemon.RelatedItemLineMarkerProvider
import com.intellij.psi.PsiElement
import com.intellij.codeInsight.navigation.NavigationGutterIconBuilder
import com.intellij.icons.AllIcons
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.jetbrains.extensions.python.toPsi
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyStatement
import sk.infinit.testmon.*
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark

/**
 * Testmon RelatedItemLineMarkerProvider fod display gutter icons.
 */
class TestmonRelatedItemLineMarkerProvider : RelatedItemLineMarkerProvider() {

    /**
     * Add Line Marker Information to Gutter area.
     */
    override fun collectNavigationMarkers(psiElement: PsiElement, resultCollection: MutableCollection<in RelatedItemLineMarkerInfo<PsiElement>>) {
        if (psiElement is PyStatement) {
            val project = psiElement.project

            val testmonErrorProvider = PsiElementErrorProvider()

            val pyFileMarks = testmonErrorProvider
                    .getFilteredPyFileMarks(psiElement, FileMarkType.GUTTER_LINK, null)

            for (fileMark in pyFileMarks) {
                val targetVirtualFile = findVirtualFile(fileMark.targetPath)

                if (targetVirtualFile != null) {
                    val targetPsiElement = findTargetPsiElement(fileMark, project, targetVirtualFile)

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

        val targetDocument = targetPsiFile.viewProvider.document

        val targetLine = fileMark.targetLine + 1

        val targetLineStartOffset: Int?

        targetLineStartOffset = if (targetLine == targetDocument?.lineCount) {
            targetDocument.getLineStartOffset(targetLine - 1)
        } else {
            targetDocument?.getLineStartOffset(targetLine)
        }

        return targetPsiFile.findElementAt(targetLineStartOffset!!)
    }
}