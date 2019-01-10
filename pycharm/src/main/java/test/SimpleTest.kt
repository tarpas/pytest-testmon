import org.junit.Test
import java.nio.file.Paths
import com.intellij.testFramework.fixtures.LightCodeInsightFixtureTestCase

class SuffixEditorLinePainterTest : LightCodeInsightFixtureTestCase() {
    @Test
    fun testGetLineExtensions() {
        this.myFixture.configureByFile("test_a_file.py")

        this.myFixture.checkResultByFile("test_a_file_decorated.py")
    }

    override fun getTestDataPath(): String {
        val path = Paths.get("").toAbsolutePath().toString() + "/src/main/java/test/testData"
        return path
    }
}
