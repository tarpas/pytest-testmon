package sk.infinit.testmon.server

import org.jetbrains.io.CustomPortServerManagerBase
import java.lang.Exception

class TestmonPortServerManager: CustomPortServerManagerBase() {

    override fun getPort(): Int {
        TODO("not implemented") //To change body of created functions use File | Settings | File Templates.
    }

    override fun cannotBind(p0: Exception?, p1: Int) {
        TODO("not implemented") //To change body of created functions use File | Settings | File Templates.
    }

    override fun isAvailableExternally(): Boolean {
        TODO("not implemented") //To change body of created functions use File | Settings | File Templates.
    }
}