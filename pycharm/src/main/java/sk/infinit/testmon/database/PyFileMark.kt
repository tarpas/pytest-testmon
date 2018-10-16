package sk.infinit.testmon.database

/**
 * Map database FileMark table to object.
 */
class PyFileMark(val id: Int, val type: String, val text: String, val fileName: String, val beginLine: Int, val beginCharacter: Int,
                 val endLine: Int, val endCharacter: Int, val checkContent: String, val targetPath: String?,
                 val targetLine: Int, val targetCharacter: Int, val gutterLinkType: String?, val exceptionId: Int)