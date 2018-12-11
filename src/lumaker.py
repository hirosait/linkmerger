#-*- using:utf-8 -*-
import logging
import sys
import time

import fiona
from shapely.geometry import mapping, shape
# import numpy as np

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# Path setting
#  new link file
newLinkShapeFile = "C:\qgis\ICP\qgis\projects\minato-ku\minato-link-new.shp"

# link shape
# linkShapeFile = "C:\ICP\qgis\projects\minato-ku\minato-link.shp"
linkShapeFile = "C:\qgis\ICP\qgis\projects\minato-ku\minato-link.shp"
# linkShapeFile = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/minato-ku/minato-link.shp"

# node shape
# nodeShapeFile = "C:\ICP\qgis\projects\minato-ku\minato-node.shp"
# nodeShapeFile = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/minato-ku/minato-node.shp"
nodeShapeFile = "C:\qgis\ICP\qgis\projects\minato-ku\minato-node.shp"

# new objectid 30,000,000からスタート
newobjectid = 30000000

from_node_links = {}
to_node_links = {}

# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count',
                   'ts_drm_tri', 'legal_spee', 'legal_sp_1')


# 属性の値が同一かチェック
def check_attributes(f, t, attributes):

    for attr in attributes:
        if f['properties'][attr] != t['properties'][attr]:
            return False
        else:
            return True


# リンクを逆向きに
def reverse_link(link):

    # 一方通行種別 正方向1,3 <=> 逆方向2,4
    if link['properties']['oneway_c'] == 1:
        link['properties']['oneway_c'] = 3
    elif link['properties']['oneway_c'] == 3:
        link['properties']['oneway_c'] = 1
    elif link['properties']['oneway_c'] == 2:
        link['properties']['oneway_c'] = 4
    elif link['properties']['oneway_c'] == 4:
        link['properties']['oneway_c'] = 2

    # リンク方向コード 1:正方向 2:逆方向
    if link['properties']['linkdir_c'] == 1:
        link['properties']['linkdir_c'] = 2
    elif link['properties']['linkdir_c'] == 2:
        link['properties']['linkdir_c'] = 1

    # coordinates listを逆順に
    link['properties']['coordinates'] = link['properties']['coordinates'][::-1]

    return link


# リンクを接合
def merge_links(a, b, node):

    # 新しいobjectid
    global newobjectid
    if newobjectid is not 30000000:
        newobjectid = newobjectid = newobjectid + 1

    # ノードの位置を特定
    aNodes = (a['properties']['fromnodeid'], a['properties']['tonodeid'])
    bNodes = (b['properties']['fromnodeid'], b['properties']['tonodeid'])
    aNodePos = aNodes.index(node)
    bNodePos = bNodes.index(node)

    # coordinates
    newc = []
    ac = a['geometry']['coordinates']
    bc = b['geometry']['coordinates']

    # 両リンクの向きを確認 同一方向に
    # <-a- n -b->  =>  -a-> n -b->
    if aNodePos == 0 and bNodePos == 0:
        a = reverse_link(a)
        bc.reverse()
        # shape
        for pos in bc:
            newc.extend(pos)
        newc.extend(ac)
        # from, to
        newfromnodeid = aNodes[1]
        newtonodeid = bNodes[1]

    # -a-> n -b->  or <-b- n <-a- =>  keep
    elif aNodePos == 1 and bNodePos == 0:
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[1]
        newc.extend(ac)
        newc.extend(bc)
    # <-a- n <-b- => or -b-> n -a-> keep
    elif aNodePos == 0 and bNodePos == 1:
        newfromnodeid = bNodes[0]
        newtonodeid = aNodes[1]
        newc.extend(bc)
        newc.extend(ac)
    # -a-> n <-b-  =>  -a-> n -b->
    elif aNodePos == 1 and bNodePos == 1:
        b = reverse_link(b)
        bc.reverse()
        # shape
        newc.extend(ac)
        for pos in bc:
            newc.extend(pos)
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[0]

    a['properties']['objectid'] = newobjectid
    a['properties']['fromnodeid'] = newfromnodeid
    a['properties']['tonodeid'] = newtonodeid
    a['geometry']['coordinates'] = newc
    return a


def write_link_shape_file(f):
    with open(linkShapeFile, 'r') as source:
        with open(newLinkShapeFile, 'w', **source.meta) as sink:
            for f in source:
                try:
                    geom = shape(f['geometry'])
                    if not geom.is_valid:
                        geom = geom.buffer(0.0)
                    f['geometry'] = mapping(geom)
                    sink.write(f)

                except Exception:
                    print(f"Error on {f['properties']['objectid']}")


def main():

    all_link_count = 0
    merged_link_count = 0
    newlinks = []

    # リンクレイヤからfromnodeid, tonodeid を取得し、Dict[objectid] 形式で辞書化　
    with fiona.collection(linkShapeFile, "r") as fl:
        for feature in fl:
            from_node_id = feature['properties']['fromnodeid']
            from_node_links[from_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            to_node_id = feature['properties']['tonodeid']
            to_node_links[to_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            all_link_count = all_link_count + 1

        # connlink=2のノードに接続しているリンクを接合する
        with fiona.collection(nodeShapeFile, "r") as fn:
            with fiona.collection(newLinkShapeFile, 'w', **fl.meta) as f:
                for feature in fn:
                    connlink = feature['properties']['connlink']
                    if connlink == 2:
                        nodeid = feature['properties']['objectid']
                        if nodeid == 1187139:
                            print('k')
                        if nodeid == 11566761:
                            print('j')
                        # 接合対象のリンクを特定し、辞書から削除
                        if nodeid in from_node_links.keys():
                            from_link = from_node_links.pop(nodeid)
                            # print(f"fromlink:{fromlink}")
                            if nodeid in to_node_links.keys():
                                to_link = to_node_links.pop(nodeid)
                                if check_attributes(from_link, to_link, checkAttributes):
                                    if from_link in newlinks:
                                        newlinks.remove(from_link)
                                    if to_link in newlinks:
                                        newlinks.remove(to_link)
                                    newlink = merge_links(from_link, to_link, nodeid)
                                    newlinks.append(newlink)
                                    new_from_node_id = newlink['properties']['fromnodeid']
                                    new_to_node_id = newlink['properties']['tonodeid']
                                    from_node_links[new_from_node_id] = newlink
                                    to_node_links[new_to_node_id] = newlink
                                    merged_link_count = merged_link_count + 1
                                    # print(f"  tolink:{tolink}")
                                    # print(f" newlink:{newlink}")

                try:
                    f.writerecords(newlinks)
                except Exception as e:
                    logging.exception(f"Error writing feature {newlink[['properties']['objectid']]}:{e}")

                print(f"Finished.  All Links counts: {all_link_count}, Generated LUs: {merged_link_count}")


if __name__ == '__main__':
    start = time.time()
    main()
    elapsed_time = time.time() - start
    print("elapsed_time: {:.3f}".format(elapsed_time) + "[sec]")

