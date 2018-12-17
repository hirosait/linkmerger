#-*- using:utf-8 -*-
import collections
from concurrent import futures
import logging
import sys
import time

import fiona
from shapely.geometry import mapping, shape
# import numpy as np

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

base_dir = "C:/ICP/qgis/projects/"
# base_dir = "C:/qgis/ICP/qgis/projects/"
# base_dir = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/"

# Path setting
#  new link file
newLinkShapeFile = base_dir + "minato-ku/minato-link-new.shp"
# newLinkShapeFile = base_dir + "/tokyo/road_link_tokyo_new.shp"

# link shape
linkShapeFile = base_dir + "minato-ku/minato-link.shp"
# linkShapeFile = base_dir + "tokyo/road_link_tokyo.shp"

# node shape
nodeShapeFile = base_dir + "minato-ku/minato-node.shp"
# nodeShapeFile = base_dir + "tokyo/road_node_tokyo.shp"

# new objectid 30,000,000からスタート
newobjectid = 30000000

from_node_links = {}
to_node_links = {}
crossing_nodes = {}
newlinks = collections.deque()
all_nodes = collections.deque()

# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count',
                   'ts_drm_tri', 'legal_spee', 'legal_sp_1')


# 属性の値が同一かチェック
def check_attributes(f, t, attributes):
    if f is None or t is None:
        return False

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


def flatten(nested_list):
    # フラットなリストとフリンジを用意
    flat_list = []
    fringe = [nested_list]
    while len(fringe) > 0:
        node = fringe.pop(0)
        # ノードがリストであれば子要素をフリンジに追加
        # リストでなければそのままフラットリストに追加
        if isinstance(node, list):
            fringe = node + fringe
        else:
            flat_list.append(node)

    return flat_list


# ジオメトリLineStringを結合し、MultiLineStringにする
def merge_linstrings(first, second):

    first_coordinates = []
    second_coordinates = []

    if first['geometry']['type'] == 'LineString':
        first_coordinates.extend(first['geometry']['coordinates'])
    else:
        first_coordinates = first['geometry']['coordinates']
    if second['geometry']['type'] == 'LineString':
        second_coordinates.extend(second['geometry']['coordinates'])
    else:
        second_coordinates = second['geometry']['coordinates']

    first_coordinates.extend(second_coordinates)
    return first_coordinates


# リンクを接合
def merge_links(a, b, node):
    # 新しいobjectid
    global newobjectid

    # ノードの位置を特定
    aNodes = (a['properties']['fromnodeid'], a['properties']['tonodeid'])
    bNodes = (b['properties']['fromnodeid'], b['properties']['tonodeid'])
    aNodePos = aNodes.index(node)
    bNodePos = bNodes.index(node)

    # coordinates
    newc = []

    # 両リンクの向きを確認 同一方向に
    # <-a- n -b->  =>  -a-> n -b->
    if aNodePos == 0 and bNodePos == 0:
        a = reverse_link(a)
        bc.reverse()
        # shape
        newc = merge_linstrings(b, a)
        # from, to
        newfromnodeid = aNodes[1]
        newtonodeid = bNodes[1]

    # -a-> n -b->  or <-b- n <-a- =>  keep
    elif aNodePos == 1 and bNodePos == 0:
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[1]
        newc = merge_linstrings(a, b)
    # <-a- n <-b- => or -b-> n -a-> keep
    elif aNodePos == 0 and bNodePos == 1:
        newfromnodeid = bNodes[0]
        newtonodeid = aNodes[1]
        newc = merge_linstrings(b, a)
    # -a-> n <-b-  =>  -a-> n -b->
    elif aNodePos == 1 and bNodePos == 1:
        b = reverse_link(b)
        bc.reverse()
        # shape
        newc = merge_linstrings(a, b)
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[0]

    a['properties']['objectid'] = newobjectid
    a['properties']['fromnodeid'] = newfromnodeid
    a['properties']['tonodeid'] = newtonodeid
    a['geometry']['coordinates'] = flatten(newc)
    return a


def get_link(node):
    # 接合対象のリンクを特定し、辞書から削除
    if node in from_node_links.keys():
        f = from_node_links.pop(node)
        # print(f"fromlink:{fromlink}")
        if node in to_node_links.keys():
            t = to_node_links.pop(node)
            return f, t
    return None, None


def remove_link(f, t):
    global newlinks
    newlinks = [x for x in newlinks if not x in (f, t)]


def make_lu(feature):
    global crossing_nodes
    nodeid = feature['properties']['objectid']
    if nodeid in crossing_nodes:
        nodeid = feature['properties']['objectid']
        from_link, to_link = get_link(nodeid)
        if check_attributes(from_link, to_link, checkAttributes):
            remove_link(from_link, to_link)
            newlink = merge_links(from_link, to_link, nodeid)
            new_from_node_id = newlink['properties']['fromnodeid']
            new_to_node_id = newlink['properties']['tonodeid']
            from_node_links[new_from_node_id] = newlink
            to_node_links[new_to_node_id] = newlink
            merged_link_count = merged_link_count + 1
            return newlink
        else:
            return False
    else:
        return False


def main():

    global newlinks, from_node_links, to_node_links, crossing_nodes
    all_link_count = 0
    merged_link_count = 0

    # リンクレイヤからfromnodeid, tonodeid を取得し、Dict[objectid] 形式で辞書化　
    with fiona.open(linkShapeFile, "r") as fl:
        print('reading nodes and links')
        for feature in fl:
            all_nodes.append(feature['properties']['fromnodeid'])
            all_nodes.append(feature['properties']['tonodeid'])
            from_node_id = feature['properties']['fromnodeid']
            from_node_links[from_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            to_node_id = feature['properties']['tonodeid']
            to_node_links[to_node_id] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
            all_link_count = all_link_count + 1

        # 2つのリンクが接続されているノードのobjectid属性を抽出
        c = collections.Counter(all_nodes)
        crossing_nodes = [k for k, v in c.items() if v == 2]

        print('start merging')
        with futures.ProcessPoolExecutor() as executor:

            with fiona.open(nodeShapeFile, "r") as fn:
                with fiona.open(newLinkShapeFile, 'w', **fl.meta) as f:
                    for feature in fn:
                        result = executor.submit(make_lu, feature)
                        if result:
                            newlinks.append(result)
                    try:
                        print('start writing')
                        # f.writerecords(newlinks)
                        for r in futures.as_completed(newlinks):
                            f.write(r.result())

                    except Exception as e:
                        logging.exception(f"Error writing :{e}")

                    print(f"Finished.  All Links counts: {all_link_count}, Generated LUs: {merged_link_count}")


if __name__ == '__main__':
    start = time.time()

    main()
    elapsed_time = time.time() - start
    print("elapsed_time: {:.3f}".format(elapsed_time) + "[sec]")

