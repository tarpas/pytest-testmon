package sk.infinit.testmon

import com.intellij.ide.IdeAboutInfoUtil
import com.intellij.notification.Notification
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.application.ex.ApplicationInfoEx
import com.intellij.openapi.fileTypes.FileTypeRegistry
import com.intellij.openapi.util.io.BufferExposingByteArrayOutputStream
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpMethod
import io.netty.handler.codec.http.HttpRequest
import io.netty.handler.codec.http.QueryStringDecoder
import org.jetbrains.ide.RestService
import java.io.IOException

/**
 * Example of JSON message http service.
 */
class MessageHttpService : RestService() {

    override fun getServiceName(): String {
        return "message"
    }

    override fun isMethodSupported(httpMethod: HttpMethod): Boolean {
        return httpMethod == HttpMethod.POST
    }

    override fun isHostTrusted(request: FullHttpRequest) = true

    override fun isAccessible(request: HttpRequest) = true

    @Throws(IOException::class)
    override fun execute(urlDecoder: QueryStringDecoder, request: FullHttpRequest, context: ChannelHandlerContext): String? {
        val jsonReader = createJsonReader(request)

        val message: Message = gson.value.fromJson(jsonReader, Message::class.java)

        Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID, "Testmon plugin", message.text, NotificationType.INFORMATION))

        val byteArrayOutputStream = getAboutJsonOutputStream(urlDecoder)

        RestService.send(byteArrayOutputStream, request, context)

        return null
    }

    @Throws(IOException::class)
    fun getAboutJsonOutputStream(urlDecoder: QueryStringDecoder?): BufferExposingByteArrayOutputStream {
        val byteArrayOutputStream = BufferExposingByteArrayOutputStream()

        val jsonWriter = RestService.createJsonWriter(byteArrayOutputStream)
        jsonWriter.beginObject()

        IdeAboutInfoUtil.writeAboutJson(jsonWriter)

        if (urlDecoder != null && RestService.getBooleanParameter("registeredFileTypes", urlDecoder)) {
            jsonWriter.name("registeredFileTypes").beginArray()

            for (fileType in FileTypeRegistry.getInstance().registeredFileTypes) {
                jsonWriter.beginObject()
                jsonWriter.name("name").value(fileType.name)
                jsonWriter.name("description").value(fileType.description)
                jsonWriter.name("isBinary").value(fileType.isBinary)
                jsonWriter.endObject()
            }

            jsonWriter.endArray()
        }

        if (urlDecoder != null && RestService.getBooleanParameter("more", urlDecoder)) {
            val appInfo = ApplicationInfoEx.getInstanceEx()

            jsonWriter.name("vendor").value(appInfo.companyName)
            jsonWriter.name("isEAP").value(appInfo.isEAP)
            jsonWriter.name("productCode").value(appInfo.build.productCode)
            jsonWriter.name("buildDate").value(appInfo.buildDate.time.time)
            jsonWriter.name("isSnapshot").value(appInfo.build.isSnapshot)
            jsonWriter.name("configPath").value(PathManager.getConfigPath())
            jsonWriter.name("systemPath").value(PathManager.getSystemPath())
            jsonWriter.name("binPath").value(PathManager.getBinPath())
            jsonWriter.name("logPath").value(PathManager.getLogPath())
            jsonWriter.name("homePath").value(PathManager.getHomePath())
        }

        jsonWriter.endObject()
        jsonWriter.close()

        return byteArrayOutputStream
    }
}