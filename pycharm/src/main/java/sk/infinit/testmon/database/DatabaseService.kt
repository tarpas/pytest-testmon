 package sk.infinit.testmon.database

import sk.infinit.testmon.logErrorMessage
import java.io.File
import java.sql.*
import java.sql.SQLException
import java.sql.ResultSet
import java.util.*

/**
 * Database service to wokr with Sqlite project files.
 */
class DatabaseService private constructor() {

    /**
     * Connection instance for current project.
     */
    private var connection: Connection? = null

    /**
     * Path to Sqlite database file
     */
    private var databaseFilePath: String? = null

    /**
     * Companion object for 'static' initialization of Sqlite JDBC driver.
     */
    companion object {
        const val FILE_MARK_TABLE_NAME = "FileMark"
        const val EXCEPTION_TABLE_NAME = "Exception"

        init {
            Class.forName("org.sqlite.JDBC")
        }

        private val databaseServiceInstance: DatabaseService = DatabaseService()

        @Synchronized
        fun getInstance(): DatabaseService {
            return databaseServiceInstance
        }
    }

    /**
     * Get PyFileMark's where type is FileMarkType.GUTTER_LINK.
     */
    fun getGutterLinkFileMarks(fileName: String, beginLine: Int): List<PyFileMark> {
        return getFileMarks(fileName, beginLine, FileMarkType.GUTTER_LINK.value)
    }

    /**
     * Get PyFileMark's list by file name (path) and with type FileMarkType.RED_UNDERLINE_DECORATION.
     */
    fun getRedUnderlineDecorationFileMarks(fileName: String): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            try {
                connection = openConnection()

                statement = connection?.prepareStatement("select * from $FILE_MARK_TABLE_NAME where file_name = ? and type = ?")

                statement?.setString(1, fileName)
                statement?.setString(2, FileMarkType.RED_UNDERLINE_DECORATION.value)

                resultSet = statement?.executeQuery()

                while (resultSet!!.next()) {
                    pyFileMarks.add(mapResultSetToPyFileMark(resultSet))
                }
            } catch (sqlException: SQLException) {
                logErrorMessage(sqlException)
            }
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        } finally {
            closeAll(connection, statement, resultSet)
        }

        return pyFileMarks
    }

    /**
     * Get PyFileMark's list by file name (path) and begin line number and with type FileMarkType.RED_UNDERLINE_DECORATION.
     */
    fun getRedUnderlineDecorationFileMarks(fileName: String, lineNumber: Int): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            try {
                connection = openConnection()

                statement = connection?.prepareStatement("select * from $FILE_MARK_TABLE_NAME where file_name = ? and begin_line = ? and type = ?")

                statement?.setString(1, fileName)
                statement?.setInt(2, lineNumber)
                statement?.setString(3, FileMarkType.RED_UNDERLINE_DECORATION.value)

                resultSet = statement?.executeQuery()

                while (resultSet!!.next()) {
                    pyFileMarks.add(mapResultSetToPyFileMark(resultSet))
                }
            } catch (sqlException: SQLException) {
                logErrorMessage(sqlException)
            }
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        } finally {
            closeAll(connection, statement, resultSet)
        }

        return pyFileMarks
    }

    /**
     * Get PyFileMark's list for PyException.
     *
     * @return List<PyFileMark>
     */
    fun getFileMarks(fileName: String, beginLine: Int, type: String): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            try {
                connection = openConnection()

                statement = connection?.prepareStatement("select * from $FILE_MARK_TABLE_NAME where file_name = ? and begin_line = ? and type = ?")

                statement?.setString(1, fileName)
                statement?.setInt(2, beginLine)
                statement?.setString(3, type)

                resultSet = statement?.executeQuery()

                while (resultSet!!.next()) {
                    pyFileMarks.add(mapResultSetToPyFileMark(resultSet))
                }
            } catch (sqlException: SQLException) {
                logErrorMessage(sqlException)
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
    fun initialize(projectRootDirectoryPath: String) {
        databaseFilePath = getProjectDatabaseFilePath(projectRootDirectoryPath)

        val isDatabaseFileExists = checkIsDatabaseFileExists()

        if (!isDatabaseFileExists) {
            throw Exception("Sqlite database file '.runtime_file' not exists.")
        }

        val isFileMarkTableExists = checkIsTableExists(FILE_MARK_TABLE_NAME)

        if (!isFileMarkTableExists) {
            throw Exception("Database table '$FILE_MARK_TABLE_NAME' not exists.")
        }

        val isExceptionTableExists = checkIsTableExists(EXCEPTION_TABLE_NAME)

        if (!isExceptionTableExists) {
            throw Exception("Database table '$EXCEPTION_TABLE_NAME' not exists.")
        }
    }

    /**
     * Close connection
     */
    fun dispose() {
        closeConnection(connection)
    }

    /**
     * Check is table exists in database.
     */
    private fun checkIsTableExists(tableName: String): Boolean {
        connection = openConnection()

        val metaData = connection?.metaData

        val resultSet = metaData?.getTables(null, null, tableName, null)

        val isTableExists = resultSet != null && resultSet.next()

        closeResultSet(resultSet)
        closeConnection(connection)

        return isTableExists
    }

    /**
     * Check is Sqlite database file exists.
     */
    private fun checkIsDatabaseFileExists(): Boolean {
        val runtimeInfoFile = File(databaseFilePath)

        return runtimeInfoFile.exists()
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
            logErrorMessage(sqlException.message!!)
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
            logErrorMessage(sqlException.message!!)
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
            logErrorMessage(sqlException.message!!)
        }

    }

    /**
     * Close connection, statement and resultSet.
     *
     * @param statement  to close.
     * @param resultSet  to close.
     */
    private fun closeAll(statement: Statement?, resultSet: ResultSet?) {
        closeResultSet(resultSet)
        closeStatement(statement)
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
    private fun getProjectDatabaseFilePath(projectRootDirectoryPath: String?) = projectRootDirectoryPath + File.separator + ".runtime_info"
}