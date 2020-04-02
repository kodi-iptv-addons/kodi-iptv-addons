SELF_PATH=`pwd`
KODI_ADDONS=~/Library/Application\ Support/Kodi/addons/

addons = $(SELF_PATH)/repository.iptv \
	$(SELF_PATH)/script.module.iptvlib \
	$(SELF_PATH)/script.video.iptv.itv \
	$(SELF_PATH)/script.video.iptv.kartina \
	$(SELF_PATH)/script.video.iptv.novoetv \
	$(SELF_PATH)/script.video.iptv.ottclub \
	$(SELF_PATH)/script.video.iptv.ottplayer\
	$(SELF_PATH)/script.video.iptv.stalker \
	$(SELF_PATH)/script.video.iptv.torrenttv \
	$(SELF_PATH)/script.video.iptv.tvteam

release: zip repo

zip:
	@find . -name *.DS_Store -type f -exec rm {} \;
	@find . -name *.pyc -type f -exec rm {} \;
	@find . -name *.pyo -type f -exec rm {} \;

	@for dir in $(addons) ; do \
		cp $$dir/addon.xml $$dir/../addon.xml.bak ; \
		cat $$dir/../addon.xml.bak | sed "s#-DEV##" > $$dir/addon.xml ; \
		version=`cat $$dir/addon.xml | grep -v 'import addon' | sed -En 's/.*version="([[:digit:]]+\.[[:digit:]]+\.[[:digit:]]+[[:alnum:]]*)"/\\1/p' | tr -d '\015\032'` ; \
		addon_name=`basename $$dir` ; \
		rm -f "$$addon_name/$$addon_name-$$version.zip" ; \
    	zip -r "$$addon_name/$$addon_name-$$version.zip" "$$addon_name" -x "*.zip" ; \
    	git add "$$addon_name/$$addon_name-$$version.zip" ; \
    	mv $$dir/../addon.xml.bak $$dir/addon.xml ; \
	done

repo:
	@echo "<?xml version=\"1.0\" encoding=\"UTF-8\"?><addons>" > $(SELF_PATH)/addons.xml.tmp
	@for dir in $(addons) ; do \
		cat $$dir/addon.xml | grep -v '<?xml' | sed "s#-DEV##" >> $(SELF_PATH)/addons.xml.tmp ; \
	done
	@echo "</addons>" >> $(SELF_PATH)/addons.xml.tmp
	@xmllint -o $(SELF_PATH)/addons.xml --format $(SELF_PATH)/addons.xml.tmp  || (echo "XML is not valid: $$?"; exit 1)
	@cat $(SELF_PATH)/addons.xml | md5 > $(SELF_PATH)/addons.xml.md5
	@rm -f $(SELF_PATH)/addons.xml.tmp

dev:
	@for dir in $(addons) ; do \
	    rm -f ${KODI_ADDONS}`basename $$dir`-DEV ; \
	    ln -s $$dir ${KODI_ADDONS}`basename $$dir`-DEV ; \
	done
