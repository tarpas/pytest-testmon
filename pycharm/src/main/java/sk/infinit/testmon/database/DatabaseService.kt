package sk.infinit.testmon.database

import java.io.File
import java.sql.*
import java.sql.ResultSet
import java.util.*

/**
 * Database service to wokr with Sqlite project files.
 *
 * Low level database API.
 */
class DatabaseService(private val databaseFilePath: String) {

    /**
     * Companion object for 'static' initialization of Sqlite JDBC driver.
     */
    companion object {
        const val DATABASE_FILE_NAME = ".runtime_info0"

        const val FILE_MARK_TABLE_NAME = "FileMark"
        const val EXCEPTION_TABLE_NAME = "Exception"

        init {
            Class.forName("org.sqlite.JDBC")
        }
    }

    /**
      * Get PyFileMark's list for PyException.
     *
     * @return List<PyFileMark>
     */
    fun getPyFileMarks(fileName: String, type: String): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            connection = openConnection() ?: return pyFileMarks

            statement = connection.prepareStatement("select * from $FILE_MARK_TABLE_NAME where file_name = ? and type = ?")

            statement?.setString(1, fileName)
            statement?.setString(2, type)

            resultSet = statement?.executeQuery()

            while (resultSet!!.next()) {
                pyFileMarks.add(mapResultSetToPyFileMark(resultSet))
            }
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
            connection = openConnection() ?: return null

            statement = connection.prepareStatement("SELECT * FROM $EXCEPTION_TABLE_NAME where exception_id = ?")

            statement?.setInt(1, exceptionId)

            resultSet = statement?.executeQuery()

            if (resultSet!!.next()) {
                return mapResultSetToPyException(resultSet)
            }
        } finally {
            closeAll(connection, statement, resultSet)
        }

        return null
    }

    /**
     * Check is [databaseFilePath] exists on file system.
     */
    private fun isDatabaseFileExists() = File(databaseFilePath).exists()

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
     * Open Sqlite database connection by full file path.
     *
     * Method check if [databaseFilePath] exists and if exists it will open
     * connection, in other case it will return null.
     */
    private fun openConnection(): Connection? {
        if (!isDatabaseFileExists()) {
            return null
        }

        return DriverManager.getConnection("jdbc:sqlite:$databaseFilePath")
    }

    /**
     * Close connection.
     *
     * @param connection to close
     */
    private fun closeConnection(connection: Connection?) {
        connection?.close()
    }

    /**
     * Close statement.
     *
     * @param statement to close
     */
    private fun closeStatement(statement: Statement?) {
        statement?.close()
    }

    /**
     * Close result set.
     *
     * @param resultSet to close
     */
    private fun closeResultSet(resultSet: ResultSet?) {
        resultSet?.close()
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
}