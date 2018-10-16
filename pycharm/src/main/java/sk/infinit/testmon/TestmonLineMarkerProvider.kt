package sk.infinit.testmon

import com.intellij.codeHighlighting.Pass
import com.intellij.codeInsight.daemon.LineMarkerInfo
import com.intellij.codeInsight.daemon.RelatedItemLineMarkerInfo
import com.intellij.codeInsight.navigation.NavigationGutterIconBuilder
import com.intellij.icons.AllIcons
import com.intellij.ide.util.PsiNavigationSupport
import com.intellij.navigation.GotoRelatedItem
import com.intellij.openapi.editor.EditorFactory
import com.intellij.openapi.editor.markup.GutterIconRenderer
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.SmartPointerManager
import com.intellij.psi.util.PsiUtilCore
import com.jetbrains.extensions.python.toPsi
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.pyi.PyiRelatedItemLineMarkerProvider
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.database.PyFileMark
import java.io.File

/**
 * Testmon LineMarkerProvider for display gutter icons.
 */
class TestmonLineMarkerProvider : PyiRelatedItemLineMarkerProvider() {

    /**
     * Add LineMarkerInfo objects for lines with pyExceptions
     */
    override fun collectNavigationMarkers(psiElement: PsiElement, itemLineMarkerInfos: MutableCollection<in RelatedItemLineMarkerInfo<PsiElement>>) {
        val project = psiElement.project
        val virtualFile = psiElement.containingFile.virtualFile

        val editor = EditorFactory.getInstance().allEditors[0]

        val offsetToLogicalPosition = editor.offsetToLogicalPosition(psiElement.textOffset)

        val projectRootVirtualFile = getProjectRootDirectoryVirtualFile(project, virtualFile)

        val databaseFilePath = getProjectDatabaseFilePath(projectRootVirtualFile)

        val databaseService = DatabaseService(databaseFilePath)

        val virtualFileRelativePath = getVirtualFileRelativePath(virtualFile, projectRootVirtualFile)

        val pyFileFullPath = projectRootVirtualFile?.path + File.separator + virtualFileRelativePath

        val fileMarks = databaseService.getGutterLinkFileMarks(pyFileFullPath, offsetToLogicalPosition.line)

        for (fileMark in fileMarks) {
            if (fileMark.checkContent == psiElement.text) {
                val targetPsiElement = getTargetPsiElement(fileMark, project)

//                val gutterIconBuilder = NavigationGutterIconBuilder
//                        .create(AllIcons.General.Error)
//                        .setTargets(targetPsiElement)
//
//                val lineMarkerInfo = gutterIconBuilder.createLineMarkerInfo(psiElement)

//                val lineMarkerInfo = LineMarkerInfo(psiElement, psiElement.textRange, AllIcons.General.Error, Pass.LINE_MARKERS, null, null, GutterIconRenderer.Alignment.LEFT)

                val lineMarkerInfo = createLineMarkerInfo(psiElement, targetPsiElement!!, fileMark.targetPath!!)

                itemLineMarkerInfos.add(lineMarkerInfo)
            }
        }
    }

    /**
     * Get target PsiElement to navigate.
     */
    private fun getTargetPsiElement(fileMark: PyFileMark, project: Project): PsiElement? {
        val targetVirtualFile = VfsUtil.findFileByIoFile(File(fileMark.targetPath), false)

        val targetPsiFile = targetVirtualFile!!.toPsi(project) as PyFile

        val targetDocument = targetPsiFile.viewProvider.document

        val targetLineStartOffset = targetDocument?.getLineStartOffset(fileMark.targetLine)

        return targetPsiFile.findElementAt(targetLineStartOffset!!)
    }

    private fun createLineMarkerInfo(element: PsiElement,
                                     relatedElement: PsiElement,
                                     itemTitle: String): RelatedItemLineMarkerInfo<PsiElement> {
        val pointerManager = SmartPointerManager.getInstance(element.project)
        val relatedElementPointer = pointerManager.createSmartPsiElementPointer(relatedElement)
        val stubFileName = relatedElement.containingFile.name

        return RelatedItemLineMarkerInfo(
                element, element.textRange, ICON, Pass.LINE_MARKERS,
                { element1 -> "$itemTitle in $stubFileName" }, { e, elt ->
            val restoredRelatedElement = relatedElementPointer.element

            val offset = if (restoredRelatedElement is PsiFile) -1 else restoredRelatedElement!!.textOffset
            val virtualFile = PsiUtilCore.getVirtualFile(restoredRelatedElement)
            if (virtualFile != null && virtualFile.isValid) {
                PsiNavigationSupport.getInstance()
                        .createNavigatable(restoredRelatedElement.project, virtualFile, offset)
                        .navigate(true)
            }
        }, GutterIconRenderer.Alignment.RIGHT, GotoRelatedItem.createItems(listOf(relatedElement)))
    }
}