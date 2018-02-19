
print("Loaded test_plugin.py")


class TestPlugin:
    consumerType = str

    def run(self):
        pass

    def configure(self, **options):
        pass


PLUGIN = TestPlugin
