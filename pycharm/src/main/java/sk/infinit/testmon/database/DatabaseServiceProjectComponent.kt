package sk.infinit.testmon.database

import com.intellij.openapi.components.ProjectComponent
import com.intellij.openapi.project.Project
import sk.infinit.testmon.getDatabaseServiceProjectComponent
import sk.infinit.testmon.logErrorMessage
import java.io.File
import java.sql.*
import java.sql.SQLException
import java.sql.ResultSet
import java.util.*

/**
 * Database service to wokr with Sqlite project files.
 *
 * Low level database API.
 */
class DatabaseServiceProjectComponent(private val project: Project) : ProjectComponent {

    /**
     * Connection instance for current project.
     */
    private var connection: Connection? = null

    /**
     * Path to Sqlite database file
     */
    private var databaseFilePath: String? = null

    /**
     * Contains state of plugin extensions for current project.
     */
    var enabled: Boolean = true

    /**
     * Companion object for 'static' initialization of Sqlite JDBC driver.
     */
    companion object {
        const val COMPONENT_NAME = "RuntimeInfoProjectComponent"
        const val FILE_MARK_TABLE_NAME = "FileMark"
        const val EXCEPTION_TABLE_NAME = "Exception"

        init {
            Class.forName("org.sqlite.JDBC")
        }

    }

    override fun getComponentName(): String {
        return COMPONENT_NAME
    }

    /**
     * Dispose DatabaseServiceProjectComponent on project closed.
     */
    override fun projectClosed() {
        this.dispose()
    }

    /**
     * Initialize DatabaseServiceProjectComponent on project open.
     */
    override fun projectOpened() {
        val isInitialized = this.initialize(project.baseDir.path)

        if (!isInitialized) {
            enabled = false

            getDatabaseServiceProjectComponent(project).dispose()

//            logErrorMessage("Not initialized.")
        } else {

            enabled = true
        }
    }


    /**
     * Get PyFileMark's list for PyException.
     *
     * @return List<PyFileMark>
     */
    fun getFileMarks(fileName: String, type: String): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            connection = openConnection()

            statement = connection?.prepareStatement("select * from $FILE_MARK_TABLE_NAME where file_name = ? and type = ?")

            statement?.setString(1, fileName)
            statement?.setString(2, type)

            resultSet = statement?.executeQuery()

            while (resultSet!!.next()) {
                pyFileMarks.add(mapResultSetToPyFileMark(resultSet))
            }
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        } finally {
            closeAll(connection, statement, resultSet)
        }

        return pyFileMarks
    }

    /**
     * Get PyException object by id.
     */
    fun getPyException(exceptionId: Int): PyException? {
        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            connection = openConnection()

            statement = connection?.prepareStatement("SELECT * FROM $EXCEPTION_TABLE_NAME where exception_id = ?")

            statement?.setInt(1, exceptionId)

            resultSet = statement?.executeQuery()

            if (resultSet!!.next()) {
                return mapResultSetToPyException(resultSet)
            }
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        } finally {
            closeAll(connection, statement, resultSet)
        }

        return null
    }

    /**
     * Map ResultSet data to PyException object.
     */
    private fun mapResultSetToPyException(resultSet: ResultSet): PyException {
        val exceptionId = resultSet.getInt("exception_id")
        val fileName = resultSet.getString("file_name")
        val line = resultSet.getInt("line")
        val exceptionText = resultSet.getString("exception_text")

        return PyException(exceptionId, fileName, line, exceptionText)
    }

    /**
     * Map ResultSet data to PyFileMark object.
     */
    private fun mapResultSetToPyFileMark(resultSet: ResultSet): PyFileMark {
        val fileMarkId = resultSet.getInt("file_mark_id")
        val type = resultSet.getString("type")
        val text = resultSet.getString("text")
        val fileName = resultSet.getString("file_name")
        val beginLine = resultSet.getInt("begin_line")
        val beginCharacter = resultSet.getInt("begin_character")
        val endLine = resultSet.getInt("end_line")
        val endCharacter = resultSet.getInt("end_character")
        val checkContent = resultSet.getString("check_content")
        val targetPath = resultSet.getString("target_path")
        val targetLine = resultSet.getInt("target_line")
        val targetCharacter = resultSet.getInt("target_character")
        val gutterLinkType = resultSet.getString("gutterLinkType")
        val exceptionId = resultSet.getInt("exception_id")

        return PyFileMark(fileMarkId, type, text, fileName, beginLine, beginCharacter, endLine,
                endCharacter, checkContent, targetPath, targetLine, targetCharacter, gutterLinkType, exceptionId)
    }

    /**
     * Initialize Database Service: open one connection for instance.
     */
    fun initialize(projectRootDirectoryPath: String): Boolean {
        databaseFilePath = getProjectDatabaseFilePath(projectRootDirectoryPath)

        return File(databaseFilePath).exists()
    }

    /**
     * Close connection
     */
    fun dispose() {
        closeConnection(connection)
    }

    /**
     * Open Sqlite database connection by full file path.
     */
    private fun openConnection(): Connection? {
        return DriverManager.getConnection("jdbc:sqlite:$databaseFilePath")
    }

    /**
     * Close connection.
     *
     * @param connection to close
     */
    private fun closeConnection(connection: Connection?) {
        try {
            if (connection != null && !connection.isClosed) {
                connection.close()
            }
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        }
    }

    /**
     * Close statement.
     *
     * @param statement to close
     */
    private fun closeStatement(statement: Statement?) {
        try {
            statement?.close()
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        }

    }

    /**
     * Close result set.
     *
     * @param resultSet to close
     */
    private fun closeResultSet(resultSet: ResultSet?) {
        try {
            resultSet?.close()
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        }

    }

    /**
     * Close connection, statement and resultSet.
     *
     * @param connection to close.
     * @param statement  to close.
     * @param resultSet  to close.
     */
    private fun closeAll(connection: Connection?, statement: Statement?, resultSet: ResultSet?) {
        closeResultSet(resultSet)
        closeStatement(statement)
        closeConnection(connection)
    }

    /**
     * Get project Sqlite database file path.
     */
    private fun getProjectDatabaseFilePath(projectRootDirectoryPath: String?) = projectRootDirectoryPath + File.separator + ".runtime_info0"
}