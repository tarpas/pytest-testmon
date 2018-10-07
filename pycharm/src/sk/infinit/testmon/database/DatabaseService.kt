package sk.infinit.testmon.database

import sk.infinit.testmon.logErrorMessage
import java.sql.*


/**
 * Database service to wokr with Sqlite project files.
 */
class DatabaseService(private val sqlLiteFilePath: String) {

    /**
     * Get PyFileMark's list for PyException.
     *
     * @return List<PyFileMark>
     */
    fun getExceptionFileMarks(exception: PyException): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            connection = openConnection()

            try {
                statement = connection?.prepareStatement("select * from FileMark where exception_id = ?")

                statement?.setInt(1, exception.id)

                resultSet = statement?.executeQuery()

                while (resultSet!!.next()) {
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

                    val fileMark = PyFileMark(fileMarkId, type, text, fileName, beginLine, beginCharacter, endLine,
                            endCharacter, checkContent, targetPath, targetLine, targetCharacter, gutterLinkType, exceptionId)

                    pyFileMarks.add(fileMark)
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
     * Get PyException objects from database file.
     *
     * @return List<PyException>
     */
    fun getPyExceptions(): List<PyException> {
        val pyExceptions: MutableList<PyException> = ArrayList()

        var connection: Connection? = null
        var statement: Statement? = null
        var resultSet: ResultSet? = null

        try {
            connection = openConnection()

            try {
                statement = connection?.createStatement()
                resultSet = statement?.executeQuery("SELECT * FROM Exception")

                while (resultSet!!.next()) {
                    val exceptionId = resultSet.getInt("exception_id")
                    val fileName = resultSet.getString("file_name")
                    val line = resultSet.getInt("line")
                    val description = resultSet.getString("description")
                    val exceptionText = resultSet.getString("exception_text")

                    val fileMarkException = PyException(exceptionId, fileName, line, description, exceptionText)

                    pyExceptions.add(fileMarkException)
                }
            } catch (sqlException: SQLException) {
                logErrorMessage(sqlException)
            }
        } catch (sqlException: SQLException) {
            logErrorMessage(sqlException)
        } finally {
            closeAll(connection, statement, resultSet)
        }

        return pyExceptions
    }

    /**
     * Open Sqlite connection.
     *
     * @return Connection?
     */
    private fun openConnection(): Connection? {
        Class.forName("org.sqlite.JDBC")

        return DriverManager.getConnection("jdbc:sqlite:$sqlLiteFilePath")
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
            if (statement != null) {
                statement.close()
            }
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