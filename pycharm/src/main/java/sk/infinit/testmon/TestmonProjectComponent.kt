package sk.infinit.testmon

import com.intellij.codeInsight.daemon.LineMarkerProvider
import com.intellij.codeInsight.daemon.LineMarkerProviders
import com.intellij.lang.ExternalLanguageAnnotators
import com.intellij.lang.LanguageExtensionPoint
import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.editor.EditorLinePainter
import com.intellij.openapi.extensions.Extensions
import com.intellij.openapi.extensions.ExtensionsArea
import com.intellij.openapi.project.Project
import com.intellij.util.containers.stream
import sk.infinit.testmon.database.DatabaseService
import sk.infinit.testmon.extensions.SuffixEditorLinePainter
import sk.infinit.testmon.extensions.RedUnderlineDecorationExternalAnnotator
import sk.infinit.testmon.extensions.GutterIconRelatedItemLineMarkerProvider

/**
 * Project component implementation for Testmon plugin.
 */
class TestmonProjectComponent(private val project: Project) : ProjectComponent {

    companion object {
        const val COMPONENT_NAME = "TestmonProjectComponent"
    }

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
            DatabaseService.getInstance().dispose()
            unregisterExtensions()

            logErrorMessage("Not initialized.")
        }
    }

    /**
     * Unregister Testmon extensions.
     */
    private fun unregisterExtensions() {
        val extensionsRootArea = Extensions.getArea(null)

        unregisterEditorLinePainter(extensionsRootArea)
        unregisterAnnotator(extensionsRootArea)
        unregisterLineMarkerProvider(extensionsRootArea)
    }

    /**
     * Unregister SuffixEditorLinePainter extension.
     */
    private fun unregisterEditorLinePainter(extensionsRootArea: ExtensionsArea) {
        val editorLinePainterExtensionPoint = extensionsRootArea
                .getExtensionPoint<EditorLinePainter>(EditorLinePainter.EP_NAME.name)

        val testmonEditorLinePainter = editorLinePainterExtensionPoint.extensions
                .stream()
                .filter { it is SuffixEditorLinePainter }
                .findAny()
                .orElse(null)

        if (testmonEditorLinePainter != null) {
            editorLinePainterExtensionPoint.unregisterExtension(testmonEditorLinePainter)
        }
    }

    /**
     * Unregister TestmonAnnotator extension.
     */
    private fun unregisterAnnotator(extensionsRootArea: ExtensionsArea) {
        val externalAnnotatorExtensionPoint = extensionsRootArea
                .getExtensionPoint(ExternalLanguageAnnotators.EP_NAME)

        val testmonAnnotator = externalAnnotatorExtensionPoint.extensions
                .stream()
                .filter { it.implementationClass == RedUnderlineDecorationExternalAnnotator::class.qualifiedName }
                .findAny()
                .orElse(null)

        if (testmonAnnotator != null) {
            externalAnnotatorExtensionPoint.unregisterExtension(testmonAnnotator)
        }
    }

    /**
     * Unregister GutterIconRelatedItemLineMarkerProvider extension.
     */
    private fun unregisterLineMarkerProvider(extensionsRootArea: ExtensionsArea) {
        val lineMarkerProviderExtensionPoint = extensionsRootArea
                .getExtensionPoint<LanguageExtensionPoint<out LineMarkerProvider>>(LineMarkerProviders.EP_NAME)

        val testmonLineMarkerProvider = lineMarkerProviderExtensionPoint.extensions
                .stream()
                .filter { it.implementationClass == GutterIconRelatedItemLineMarkerProvider::class.qualifiedName }
                .findAny()
                .orElse(null)

        if (testmonLineMarkerProvider != null) {
            lineMarkerProviderExtensionPoint.unregisterExtension(testmonLineMarkerProvider)
        }
    }
}