package testmon.infinit.testmon

import com.intellij.openapi.components.ServiceManager
import com.intellij.testFramework.fixtures.*
import org.junit.Test
import sk.infinit.testmon.Config
import java.nio.file.Paths
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.services.cache.Cache
import sk.infinit.testmon.database.PyException


class RedUnderlineDecorationExternalAnnotatorTest : LightPlatformCodeInsightFixtureTestCase() {
    private val testFile = "test_file_underline.py"
    private val testFilePath = "/src/$testFile"

    private fun createPyFileMarkFixture(cacheService : Cache) {
        val fullPyFilePath = testFilePath
        val fileMarkType = FileMarkType.RED_UNDERLINE_DECORATION
        val keyPair = Pair(fullPyFilePath, fileMarkType)

        val pyFileMark = PyFileMark(
                id = 1,
                type = "RedUnderLineDecoration",
                text = "AssertionError: assert (1 + 2) == 4",
                fileName = this.testFilePath,
                beginLine = 2,
                beginCharacter = 0,
                endLine = 2,
                endCharacter = 21,
                checkContent = "    assert 1 + 2 == 4",
                targetPath = null,
                targetLine = 0,
                targetCharacter = 0,
                gutterLinkType = null,
                exceptionId = 1
        )

        val pyException = PyException(
                id = 1,
                fileName = this.testFilePath,
                lineNumber = 2,
                exceptionText = "AssertionError: assert (1 + 2) == 4"
        )
        pyFileMark.exception = pyException

        val pyFileMarks = listOf(pyFileMark)

        cacheService.setPyFileMarksCache(keyPair, pyFileMarks)
    }

    @Test
    fun testUnderlineDecoration() {
        val cacheService = ServiceManager.getService(this.myFixture.project, Cache::class.java)
        createPyFileMarkFixture(cacheService)

        val psiFile = this.myFixture.configureByFile(this.testFile)

        this.myFixture.testHighlighting(false, false, false, psiFile.virtualFile)
    }

    override fun getTestDataPath(): String {
        return Paths.get("").toAbsolutePath().toString() + Config.testDataPath
    }
}
