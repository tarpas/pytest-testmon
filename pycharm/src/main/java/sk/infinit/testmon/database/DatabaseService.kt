package sk.infinit.testmon.database

import sk.infinit.testmon.logErrorMessage
import java.sql.*


/**
 * Database service to wokr with Sqlite project files.
 */
class DatabaseService(private val sqlLiteFilePath: String) {

    /**
     * Companion object for 'static' initialization of Sqlite JDBC driver.
     */
    companion object {
        init {
            Class.forName("org.sqlite.JDBC")
        }

        const val NAME = "DatabaseService"
    }

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
            try {
                connection = openConnection()

                statement = connection?.prepareStatement("select * from FileMark where exception_id = ?")

                statement?.setInt(1, exception.id)

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
     * Get PyFileMark's where type is FileMarkType.GUTTER_LINK.
     */
    fun getGutterLinkFileMarks(fileName: String, beginLine: Int): List<PyFileMark> {
        return getFileMarks(fileName, beginLine, FileMarkType.GUTTER_LINK.value)
    }

    /**
     * Get PyFileMark's list by file name (path) and with type FileMarkType.RED_UNDERLINE_DECORATION.
     */
    fun getRedUnderlineDecorationFileMarksByFileName(fileName: String): List<PyFileMark> {
        val pyFileMarks: MutableList<PyFileMark> = ArrayList()

        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            try {
                connection = openConnection()

                statement = connection?.prepareStatement("select * from FileMark where file_name = ? and type = ?")

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

                statement = connection?.prepareStatement("select * from FileMark where file_name = ? and begin_line = ? and type = ?")

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
            try {
                connection = openConnection()

                statement = connection?.createStatement()
                resultSet = statement?.executeQuery("SELECT * FROM Exception")

                while (resultSet!!.next()) {
                    pyExceptions.add(mapResultSetToPyException(resultSet))
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
     * Get PyException object by id.
     */
    fun getPyException(exceptionId: Int): PyException? {
        var connection: Connection? = null
        var statement: PreparedStatement? = null
        var resultSet: ResultSet? = null

        try {
            try {
                connection = openConnection()

                statement = connection?.prepareStatement("SELECT * FROM Exception where exception_id = ?")

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
        val description = resultSet.getString("description")
        val exceptionText = resultSet.getString("exception_text")

        val fileMarkException = PyException(exceptionId, fileName, line, description, exceptionText)
        return fileMarkException
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
     * Open Sqlite connection.
     *
     * @return Connection?
     */
    private fun openConnection(): Connection? {
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
}