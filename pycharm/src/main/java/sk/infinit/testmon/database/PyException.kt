package sk.infinit.testmon.database

/**
 * Map database Exception table to object.
 */
class PyException(val id: Int, val fileName: String, val lineNumber: Int, val description: String, val exceptionText: String)