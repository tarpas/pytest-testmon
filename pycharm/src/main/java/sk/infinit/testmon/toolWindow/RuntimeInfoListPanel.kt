package sk.infinit.testmon.toolWindow

import com.intellij.ui.components.JBList
import java.awt.BorderLayout
import javax.swing.DefaultListModel
import javax.swing.JPanel

/**
 * [JPanel] with runtime info [JBList] items.
 */
class RuntimeInfoListPanel : JPanel() {

    /**
     * List model for runtime info JBList.
     */
    val listModel = DefaultListModel<String>()

    /**
     * Initialize panel.
     */
    init {
        layout = BorderLayout()

        val runtimeInfoFilesList = JBList(listModel)

        add(runtimeInfoFilesList, BorderLayout.CENTER)
    }
}