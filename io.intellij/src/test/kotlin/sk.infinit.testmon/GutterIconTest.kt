package sk.infinit.testmon

import com.intellij.openapi.components.ServiceManager
import com.intellij.testFramework.fixtures.LightPlatformCodeInsightFixtureTestCase
import org.junit.Test
import sk.infinit.testmon.Config
import sk.infinit.testmon.database.FileMarkType
import sk.infinit.testmon.database.PyFileMark
import sk.infinit.testmon.services.cache.Cache
import java.nio.file.Paths


class GutterIconTest : LightPlatformCodeInsightFixtureTestCase() {
    private val testFile = "test_file_gutter.py"
    private val testFilePath = "/src/$testFile"

    private fun createPyFileMarkFixture(cacheService : Cache) {
        val fileMarkType = FileMarkType.GUTTER_LINK
        val keyPair = Pair(testFilePath, fileMarkType)

        val pyFileMark = PyFileMark(
                id = 1,
                type = "GutterLink",
                text = null,
                fileName = this.testFilePath,
                beginLine = 5,
                beginCharacter = 0,
                endLine = 0,
                endCharacter = 0,
                checkContent = "    a()",
                targetPath = this.testFile,
                targetLine = 8,
                targetCharacter = 0,
                gutterLinkType = "U",
                exceptionId = 1
        )
        pyFileMark.dbDir = this.testDataPath

        val pyFileMarks = listOf(pyFileMark)

        cacheService.setPyFileMarksCache(keyPair, pyFileMarks)
    }

    @Test
    fun testGutterIcon() {
        val cacheService = ServiceManager.getService(this.myFixture.project, Cache::class.java)

        this.myFixture.configureByFile(this.testFile)

        createPyFileMarkFixture(cacheService)

        val gutterList = this.myFixture.findAllGutters()
        assert(gutterList.size == 1)
    }

    override fun getTestDataPath(): String {
        return Paths.get("").toAbsolutePath().toString() + Config.testDataPath
    }
}
