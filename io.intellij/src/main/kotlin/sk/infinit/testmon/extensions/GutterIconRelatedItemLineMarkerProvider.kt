package sk.infinit.testmon.extensions

import com.intellij.codeInsight.daemon.RelatedItemLineMarkerInfo
import com.intellij.codeInsight.daemon.RelatedItemLineMarkerProvider
import com.intellij.psi.PsiElement
import com.intellij.codeInsight.navigation.NavigationGutterIconBuilder
import com.intellij.openapi.components.ServiceManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.jetbrains.extensions.python.toPsi
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyStatement
import sk.infinit.testmon.*
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.GutterIconType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.services.cache.Cache
import java.io.File
import javax.swing.Icon

/**
 * Testmon RelatedItemLineMarkerProvider fod display gutter icons.
 */
class GutterIconRelatedItemLineMarkerProvider : RelatedItemLineMarkerProvider() {

    class Gutter(val gutterIconPsiElement: PsiElement,
                 val targetPsiElement: PsiElement,
                 val targetVirtualFile: VirtualFile,
                 val fileMark: PyFileMark)

    // At every psi element (on every line) could be two types of gutter icons ('up' and 'down')
    private lateinit var upGutters: MutableList<Gutter>
    private lateinit var downGutters: MutableList<Gutter>

    /**
     * Add Line Marker Information to Gutter area.
     */
    override fun collectNavigationMarkers(psiElement: PsiElement, resultCollection: MutableCollection<in RelatedItemLineMarkerInfo<PsiElement>>) {
        if (psiElement is PyStatement) {
            val project = psiElement.project

            val cacheService = ServiceManager.getService(project, Cache::class.java)
                    ?: return

            val fileAbsolutePath = psiElement.containingFile.virtualFile.path

            val pyFileMarks = cacheService.getPyFileMarks(fileAbsolutePath, FileMarkType.GUTTER_LINK) ?: return

            val document = PsiDocumentManager.getInstance(project).getDocument(psiElement.containingFile) ?: return
            val elementLineNumber = document.getLineNumber(psiElement.textOffset)

            val actualTargetLines = arrayListOf<Int>()

            clearGutterLists()

            for (fileMark in pyFileMarks) {
                val targetFileFullPath = fileMark.dbDir + File.separator + fileMark.targetPath
                val targetVirtualFile = findVirtualFile(targetFileFullPath)

                val fileMarkContent = fileMark.checkContent.trim()

                if (targetVirtualFile != null && fileMark.beginLine == elementLineNumber
                        && fileMarkContent == psiElement.text && fileMark.targetLine !in actualTargetLines) {

                    val targetPsiElement = findTargetPsiElement(fileMark, project, targetVirtualFile) ?: continue

                    val leafElement =  getFirstLeafElement(psiElement)

                    val gutterIcon = Gutter(leafElement, targetPsiElement, targetVirtualFile, fileMark)

                    if (fileMark.gutterLinkType == GutterIconType.DOWN.value) {
                        this.downGutters.add(gutterIcon)
                    } else {
                        this.upGutters.add(gutterIcon)
                    }

                    // Cache target lines to check for 'same target line' duplicates
                    actualTargetLines.add(fileMark.targetLine)
                }
            }

            applyGuttersWithShortestStacktrace(resultCollection)
        }
    }


    private fun clearGutterLists() {
        this.upGutters = mutableListOf()
        this.downGutters = mutableListOf()
    }

    private fun getFirstLeafElement(psiElement: PsiElement): PsiElement {
        val firstChild = psiElement.firstChild
        return if (firstChild  == null){
            psiElement
        } else {
            getFirstLeafElement(firstChild)
        }
    }

    /**
     * Get target PsiElement to navigate.
     */
    private fun findTargetPsiElement(fileMark: PyFileMark, project: Project, targetVirtualFile: VirtualFile): PsiElement? {
        val targetPsiFile = targetVirtualFile.toPsi(project) as PyFile

        val document = targetPsiFile.viewProvider.document ?: return null

        if (fileMark.targetLine >= document.lineCount) {
            return null
        }

        val targetPsiElement = targetPsiFile.findElementAt(document.getLineStartOffset(fileMark.targetLine))

        return targetPsiElement?.nextSibling
    }

    private fun applyGuttersWithShortestStacktrace(resultCollection: MutableCollection<in RelatedItemLineMarkerInfo<PsiElement>>) {
        val shortestDownGutter = getGutterWithShortestStacktrace(this.downGutters)
        val shortestUpGutter = getGutterWithShortestStacktrace(this.upGutters)

        if (shortestDownGutter != null) {
            applyGutter(shortestDownGutter, Icons.MOVE_DOWN_ARROW, resultCollection)
        }

        if (shortestUpGutter != null) {
            applyGutter(shortestUpGutter, Icons.MOVE_UP_ARROW, resultCollection)
        }
    }

    private fun getGutterWithShortestStacktrace(gutters: MutableList<Gutter>): Gutter? {
        return gutters.minWith(Comparator { g1, g2 ->
            when {
                g1.fileMark.exception?.stacktraceLength!! > g2.fileMark.exception?.stacktraceLength!! -> 1
                g1.fileMark.exception?.stacktraceLength!! == g2.fileMark.exception?.stacktraceLength!! -> 0
                else -> -1
            }
        })
    }

    private fun applyGutter(gutter: Gutter, gutterIcon: Icon, resultCollection: MutableCollection<in RelatedItemLineMarkerInfo<PsiElement>>) {
        val navigationGutterIconBuilder = NavigationGutterIconBuilder
                .create(gutterIcon)
                .setTargets(gutter.targetPsiElement)
                .setTooltipText("File ${gutter.targetVirtualFile.name}, Line ${gutter.fileMark.targetLine}")
        resultCollection.add(navigationGutterIconBuilder.createLineMarkerInfo(gutter.gutterIconPsiElement))
    }
}