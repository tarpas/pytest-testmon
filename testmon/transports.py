class Transport:
    """A storage that results are written to, with the execution opened there."""

    def __init__(self, database, exec_id):
        self.database = database
        self.exec_id = exec_id

    def insert_test_file_fps(self, tests_deps_n_outcomes):
        self.database.insert_test_file_fps(tests_deps_n_outcomes, self.exec_id)

    def delete_test_executions(self, test_names):
        self.database.delete_test_executions(test_names, self.exec_id)

    def finish_execution(self, duration, select):
        self.database.finish_execution(self.exec_id, duration, select)

    def unknown_tests(self, test_names):
        return set(test_names) - set(self.database.all_test_executions(self.exec_id))

    def close(self):
        self.database.close()


class Transports:
    """Write to every transport in order; each fails the way its storage does."""

    def __init__(self, transports):
        self.transports = transports

    def insert_test_file_fps(self, tests_deps_n_outcomes):
        for transport in self.transports:
            transport.insert_test_file_fps(tests_deps_n_outcomes)

    def delete_test_executions(self, test_names):
        for transport in self.transports:
            transport.delete_test_executions(test_names)

    def finish_execution(self, duration, select):
        for transport in self.transports:
            transport.finish_execution(duration, select)

    def insert_tests_unknown_to_mirrors(self, test_names, records):
        """Give every mirror a record of the tests of `test_names` it does not know.

        The first transport selects the tests of a run, and only those are written. A test
        that it knows and does not select never reaches a mirror that starts later or missed
        a run. A local run would then skip that test for good: with its file, which looks
        unchanged as long as the tests the mirror does know there are unaffected.
        """
        for mirror in self.transports[1:]:
            unknown = mirror.unknown_tests(test_names)
            if unknown:
                mirror.insert_test_file_fps(records(unknown))

    def close(self):
        for transport in self.transports:
            transport.close()
