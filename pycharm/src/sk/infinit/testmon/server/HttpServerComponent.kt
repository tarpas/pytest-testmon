package sk.infinit.testmon.server

import com.intellij.openapi.components.ProjectComponent
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpHandler
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.io.IOException

/**
 * Simple Java HttpServer example.
 */
class HttpServerComponent: ProjectComponent {

    private var httpServer: HttpServer? = null

    override fun getComponentName(): String {
        return "TestmonHttpServer"
    }

    override fun disposeComponent() {
        httpServer?.stop(0)
    }

    override fun initComponent() {
        val httpServer = HttpServer.create(InetSocketAddress(8099), 0)

        httpServer.createContext("/testmon", TestmonHttpHandler())
        httpServer.executor = null // creates a default executor

        httpServer.start()
    }

    internal class TestmonHttpHandler : HttpHandler {

        @Throws(IOException::class)
        override fun handle(httpExchange: HttpExchange) {
            val response = "This is the response"

            httpExchange.sendResponseHeaders(200, response.length.toLong())

            val outputStream = httpExchange.responseBody

            outputStream.write(response.toByteArray())
            outputStream.close()
        }
    }
}